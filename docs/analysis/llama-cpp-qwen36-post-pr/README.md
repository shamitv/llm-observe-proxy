# llama.cpp Qwen3.6 Post-PR Analysis

Date: 2026-05-03

This directory collects the post-PR notes for the Qwen reasoning/tool-call
failure observed through Copilot and `llm-observe-proxy`.

## Reading Order

1. [Repro/test/fix guide](./repro-test-fix-guide.md)

   Concrete fixtures for a llama.cpp developer: sample OpenAI-compatible
   requests, expected versus actual outputs, failing test ideas, implementation
   guidance, and validation steps.

2. [Framework comparison](./framework-comparison.md)

   How vLLM, SGLang, Transformers, and TGI handle the same reasoning/content/tool
   boundary, and what that implies for the llama.cpp fix.

## Related Earlier Notes

- [Original Copilot tool-calling analysis](../llama-cpp-qwen36-copilot-tool-calling.md)
- [Root cause and solution analysis](../llama-cpp-qwen36-copilot-root-cause-solution.md)
- [Tool-calling fix impact](../llama-cpp-qwen36-copilot-tool-calling-fix-impact.md)
- [Upstream PR draft](../llama-cpp-qwen36-upstream-pr-draft.md)

## Bottom Line

The captured failures point to two different problems:

- Qwen sometimes emits malformed tool arguments, which is a model compliance or
  constrained-decoding problem.
- llama.cpp returns post-`</think>` Qwen tool-call syntax as reasoning and ends
  with an empty successful assistant turn, which is an OpenAI compatibility
  parsing problem.
