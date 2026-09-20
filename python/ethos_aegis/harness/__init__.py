"""
ethos_aegis.harness — The 12-component production agent harness.

Canonical formula (Vivek Trivedy / LangChain):
    "If you're not the model, you're the harness."

Components
----------
1.  Orchestration Loop   — orchestrator.AegisHarness.run()
2.  Tools                — tools.ToolRegistry / @tool decorator
3.  Memory               — memory.MemoryStore (3-tier: index/detail/transcript)
4.  Context Management   — context.ContextManager (compaction, masking, JIT)
5.  Prompt Construction  — context.ContextManager.assemble()
6.  Output Parsing       — output_parser.OutputParser (native + ReAct fallback)
7.  State Management     — state.CheckpointStore (Ralph Loop progress files)
8.  Error Handling       — errors.ErrorCategory / with_retry / ToolExecutionError
9.  Guardrails & Safety  — guardrails.GuardrailLayer (input/output/tool tripwire)
10. Verification Loops   — verification.VerificationEngine (rules + LLM-as-judge)
11. Subagent Orchestration — orchestrator.AegisHarness.spawn_subagent()
12. Types & Config       — types.HarnessConfig / HarnessState / ToolSchema / …

Quick start
-----------
    from ethos_aegis.harness import AegisHarness, HarnessConfig
    from ethos_aegis.harness.tools import tool

    @tool("read_file", "Read a file from disk",
          parameters={"type": "object",
                      "properties": {"path": {"type": "string"}},
                      "required": ["path"]})
    def read_file(path: str) -> str:
        return open(path).read()

    harness = AegisHarness(adapter=my_adapter)
    harness.tools.register(read_file)

    for event in harness.run("Summarise the README"):
        print(event)
"""

from .orchestrator  import AegisHarness
from .types         import (
    HarnessConfig, HarnessState, HarnessConfig,
    Message, Role, ToolCall, ToolResult, ToolSchema,
    MemoryEntry, TerminationReason, VerificationResult,
)
from .tools         import ToolRegistry, tool
from .memory        import MemoryStore
from .context       import ContextManager
from .output_parser import OutputParser, ParsedOutput
from .state         import CheckpointStore
from .errors        import (
    ErrorCategory, HarnessError, ToolExecutionError, with_retry
)
from .guardrails    import GuardrailLayer, HarnessHalted
from .verification  import VerificationEngine

__all__ = [
    "AegisHarness",
    "HarnessConfig", "HarnessState",
    "Message", "Role", "ToolCall", "ToolResult", "ToolSchema",
    "MemoryEntry", "TerminationReason", "VerificationResult",
    "ToolRegistry", "tool",
    "MemoryStore",
    "ContextManager",
    "OutputParser", "ParsedOutput",
    "CheckpointStore",
    "ErrorCategory", "HarnessError", "ToolExecutionError", "with_retry",
    "GuardrailLayer", "HarnessHalted",
    "VerificationEngine",
]
