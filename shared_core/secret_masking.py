"""
Secret masking utilities for token obfuscation.
"""

def mask_token(token: str) -> str:
    """
    Mask a token for safe logging/storage.
    
    Args:
        token: Token string to mask
        
    Returns:
        Masked token string (shows first 8 and last 4 characters)
    """
    if not token or len(token) < 12:
        return "***"
    
    return f"{token[:8]}...{token[-4:]}"
