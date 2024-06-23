FormatCoders = {}

def register_coders():
    from .base_prompts import CoderPrompts
    from .editblock_coder import EditBlockCoder
    from .editblock_prompts import EditBlockPrompts
    from .editblock_fenced_coder import EditBlockFencedCoder
    from .editblock_fenced_prompts import EditBlockFencedPrompts
    from .udiff_coder import UnifiedDiffCoder
    from .udiff_prompts import UnifiedDiffPrompts
    from .wholefile_coder import WholeFileCoder
    from .wholefile_prompts import WholeFilePrompts

    FormatCoders.update({
        "diff": {
            "coder": EditBlockCoder,
            "prompts": EditBlockPrompts,
        },
        "diff-fenced": {
            "coder": EditBlockFencedCoder,
            "prompts": EditBlockFencedPrompts,
        },
        "whole": {
            "coder": WholeFileCoder,
            "prompts": WholeFilePrompts,
        },
        "udiff": {
            "coder": UnifiedDiffCoder,
            "prompts": UnifiedDiffPrompts,
        },
    })
    