"""Validates configuration for production safety."""
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def validate_production_config() -> list[str]:
    """
    Check configuration for production safety issues.

    Returns:
        List of warning messages (empty if all checks pass)
    """
    warnings = []

    # Check for development mode indicators
    if os.getenv("DEBUG", "").lower() == "true":
        warnings.append("⚠️  DEBUG mode is enabled - not recommended for production")

    # Check for default secrets
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if api_key in ["", "your_anthropic_api_key_here", "test-key"]:
        warnings.append("⚠️  ANTHROPIC_API_KEY not set or using default value")

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if bot_token in ["", "your_bot_token_here", "test-token"]:
        warnings.append("⚠️  TELEGRAM_BOT_TOKEN not set or using default value")

    # Check for permissive access controls
    allowed_users = os.getenv("ALLOWED_USERS", "")
    if not allowed_users or allowed_users == "*":
        warnings.append("⚠️  ALLOWED_USERS not configured or set to wildcard (*)")

    # Check for missing cost limits
    if not os.getenv("DAILY_COST_LIMIT"):
        warnings.append("⚠️  DAILY_COST_LIMIT not set - costs are unbounded")

    if not os.getenv("MONTHLY_COST_LIMIT"):
        warnings.append("⚠️  MONTHLY_COST_LIMIT not set - costs are unbounded")

    # Check for weak session timeout
    timeout_str = os.getenv("SESSION_TIMEOUT_MINUTES", "60")
    try:
        timeout = int(timeout_str)
        if timeout > 120:
            warnings.append(f"⚠️  SESSION_TIMEOUT_MINUTES is {timeout} (>2 hours) - memory leak risk")
    except ValueError:
        warnings.append(f"⚠️  SESSION_TIMEOUT_MINUTES has invalid value: {timeout_str}")

    # Check for insecure database location
    db_path = os.getenv("AGENTLAB_DB_PATH", "")
    if db_path and "/tmp/" in db_path:
        warnings.append("⚠️  Database in /tmp/ - data will be lost on reboot")

    # Check for log level
    log_level = os.getenv("LOG_LEVEL", "INFO")
    if log_level == "DEBUG":
        warnings.append("⚠️  LOG_LEVEL is DEBUG - verbose output in production")

    # Check for monitoring auto-restart in production
    auto_restart = os.getenv("MONITORING_AUTO_RESTART", "").lower()
    if auto_restart == "true":
        warnings.append("⚠️  MONITORING_AUTO_RESTART is enabled - should be disabled in production")

    return warnings


def check_and_warn():
    """Check configuration and log warnings at startup."""
    warnings = validate_production_config()

    if warnings:
        logger.warning("=" * 80)
        logger.warning("PRODUCTION CONFIGURATION WARNINGS:")
        for warning in warnings:
            logger.warning(warning)
        logger.warning("=" * 80)
        logger.warning("Review .env file and environment variables before deploying.")
        logger.warning("=" * 80)
    else:
        logger.info("✓ Production configuration checks passed")
