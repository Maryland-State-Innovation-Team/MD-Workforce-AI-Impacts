"""Shared LLM client setup and structured-output query helpers.

Supported providers (``-m/--model`` on each script):
  - ``claude``: Anthropic Claude via AWS Bedrock, authenticated with AWS SSO
  - ``gemini``: Google Gemini via the google-genai SDK
  - ``gpt``:    OpenAI via the Responses API
"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = REPO_ROOT / "input"
OUTPUT_DIR = REPO_ROOT / "output"

PROVIDERS = ("claude", "gemini", "gpt")

# Model IDs can be overridden in .env without code changes.
DEFAULT_MODELS = {
    "claude": "us.anthropic.claude-haiku-5-5",
    "gemini": "gemini-3.8-flash",
    "gpt": "gpt-6-luna",
}

# Gemini free tier is rate limited; set GEMINI_MIN_INTERVAL=0 on a paid tier.
DEFAULT_WORKERS = {"claude": 64, "gemini": 1, "gpt": 16}

MAX_RETRIES = 3


def model_id(provider):
    return os.getenv(f"{provider.upper()}_MODEL", DEFAULT_MODELS[provider])


def add_common_args(parser):
    parser.add_argument("-m", "--model", choices=PROVIDERS, default="claude",
                        help="LLM provider to use (default: claude)")
    parser.add_argument("-w", "--workers", type=int, default=None,
                        help="Number of concurrent requests (default depends on provider)")
    return parser


def get_client(provider):
    """Build an SDK client for the provider, or exit with a helpful message."""
    load_dotenv()  # finds python/.env or a repo-root .env
    if provider == "claude":
        import anthropic
        # AnthropicBedrock resolves credentials through boto3, so AWS_PROFILE
        # pointing at an SSO profile works after `aws sso login`.
        # An empty AWS_CA_BUNDLE (tolerated by the AWS CLI) makes botocore
        # raise InvalidConfigError, so treat it as unset.
        if "AWS_CA_BUNDLE" in os.environ and not os.environ["AWS_CA_BUNDLE"].strip():
            del os.environ["AWS_CA_BUNDLE"]
        region = os.getenv("AWS_REGION", "us-east-1")
        return anthropic.AnthropicBedrock(aws_region=region, timeout=120.0, max_retries=4)
    if provider == "gemini":
        from google import genai
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            sys.exit("Please provide a GEMINI_API_KEY in a .env file.")
        return genai.Client(api_key=key)
    if provider == "gpt":
        from openai import OpenAI
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            sys.exit("Please provide an OPENAI_API_KEY in a .env file.")
        return OpenAI(api_key=key, max_retries=4)
    raise ValueError(f"Unknown provider: {provider}")


def _query_claude(client, system_prompt, user_content, response_format):
    response = client.messages.parse(
        model=model_id("claude"),
        max_tokens=16000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
        output_format=response_format,
        output_config={"effort": os.getenv("CLAUDE_EFFORT", "low")},
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude refused: {response.stop_details}")
    return response.parsed_output.model_dump()


_gemini_last_call = [0.0]


def _query_gemini(client, system_prompt, user_content, response_format):
    # Free tier allows ~15 requests/minute; pace calls unless told otherwise.
    min_interval = float(os.getenv("GEMINI_MIN_INTERVAL", "4"))
    wait = _gemini_last_call[0] + min_interval - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _gemini_last_call[0] = time.monotonic()
    response = client.models.generate_content(
        model=model_id("gemini"),
        contents=user_content,
        config={
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
            "response_schema": response_format,
            # 3.8 Flash defaults to medium thinking; 'minimal' is not supported.
            "thinking_config": {"thinking_level": os.getenv("GEMINI_THINKING_LEVEL", "low")},
        },
    )
    if response.parsed is None:
        raise ValueError(f"Gemini returned unparseable output: {response.text!r}")
    return response.parsed.model_dump()


def _query_gpt(client, system_prompt, user_content, response_format):
    response = client.responses.parse(
        model=model_id("gpt"),
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        text_format=response_format,
        reasoning={"effort": os.getenv("GPT_REASONING_EFFORT", "low")},
    )
    if response.output_parsed is None:
        raise ValueError("OpenAI returned no parsed output (possible refusal).")
    return response.output_parsed.model_dump()


_QUERY_FNS = {"claude": _query_claude, "gemini": _query_gemini, "gpt": _query_gpt}


def _is_auth_error(exc):
    try:
        import botocore.exceptions as bce
        import anthropic
    except ImportError:
        return False
    return isinstance(exc, (
        anthropic.AuthenticationError,
        anthropic.PermissionDeniedError,
        bce.SSOTokenLoadError,
        bce.NoCredentialsError,
        bce.TokenRetrievalError,
        bce.UnauthorizedSSOTokenError,
    ))


def query(provider, client, system_prompt, user_content, response_format):
    """Return the structured response as a dict, or None after repeated failures.

    The SDKs already retry transient HTTP errors; this adds retries for schema/
    parse failures and pauses (rather than failing) when an AWS SSO token expires.
    """
    fn = _QUERY_FNS[provider]
    attempt = 0
    while True:
        try:
            return fn(client, system_prompt, user_content, response_format)
        except Exception as e:
            if _is_auth_error(e):
                tqdm.write(f"AWS/Bedrock authentication error ({type(e).__name__}): {e}\n"
                           "Run `aws sso login --profile <profile>`; retrying in 60s...")
                time.sleep(60)
                continue
            attempt += 1
            if attempt >= MAX_RETRIES:
                tqdm.write(f"Giving up on {user_content!r}: {type(e).__name__}: {e}")
                return None
            time.sleep(2 ** attempt)


def query_many(provider, client, system_prompt, user_contents, response_format, workers=None, desc=None):
    """Run ``query`` over many inputs concurrently, preserving input order."""
    workers = workers or DEFAULT_WORKERS[provider]
    if not user_contents:
        return []
    run = lambda content: query(provider, client, system_prompt, content, response_format)
    with tqdm(total=len(user_contents), desc=desc) as pbar:
        # One sequential call first so credentials (e.g. AWS SSO) and connections
        # are initialized once, instead of racing across every worker thread.
        results = [run(user_contents[0])]
        pbar.update(1)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for result in pool.map(run, user_contents[1:]):
                results.append(result)
                pbar.update(1)
    return results
