"""LLMLingua prompt compressor wrapper for LLMContext."""

from __future__ import annotations

from typing import Any


class ContextCompressor:
    """Encapsulates LLMLingua-2 prompt compression.
    
    Prevents scattering LLMLingua dependencies throughout engine code.
    """

    def __init__(
        self,
        model_name: str = "microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
        device_map: str = "cpu",
        use_llmlingua2: bool = True,
    ) -> None:
        self.model_name = model_name
        self.device_map = device_map
        self.use_llmlingua2 = use_llmlingua2
        self._compressor = None

    def _get_compressor(self):
        if self._compressor is None:
            from llmlingua import PromptCompressor
            self._compressor = PromptCompressor(
                model_name=self.model_name,
                device_map=self.device_map,
                use_llmlingua2=self.use_llmlingua2,
            )
        return self._compressor

    def compress(
        self,
        context: str,
        target_rate: float = 0.33,
        force_tokens: list[str] | None = None,
    ) -> str:
        """Compress raw text context using LLMLingua-2.

        Args:
            context: Raw text prompt / context string.
            target_rate: Target compression ratio (e.g. 0.33 = ~33% preserved).
            force_tokens: List of tokens/characters to preserve forcibly.

        Returns:
            Compressed prompt text string.
        """
        if not context:
            return context

        if force_tokens is None:
            force_tokens = ["\n", ":", "/", "_"]

        compressor = self._get_compressor()
        result = compressor.compress_prompt(
            context,
            rate=target_rate,
            force_tokens=force_tokens,
        )
        res = result.get("compressed_prompt", context)
        return str(res) if res is not None else context

    def compress_serialized_dict(
        self,
        serialized_context: dict[str, Any],
        target_rate: float = 0.33,
        force_tokens: list[str] | None = None,
    ) -> dict[str, Any]:
        """Compress structured elements within a serialized LLMContext dictionary.

        Args:
            serialized_context: The serialized LLMContext dictionary.
            target_rate: Target compression ratio.
            force_tokens: Mandatory preserved tokens.

        Returns:
            New dictionary with compressed strings.
        """
        if not serialized_context:
            return serialized_context

        if force_tokens is None:
            force_tokens = ["\n", ":", "/", "_"]

        compressed_context = dict(serialized_context)

        # 1. Compress string table 'st' if present
        if "st" in serialized_context and isinstance(serialized_context["st"], list):
            compressed_st = []
            for s in serialized_context["st"]:
                if isinstance(s, str) and len(s) > 20:
                    compressed_st.append(
                        self.compress(s, target_rate=target_rate, force_tokens=force_tokens)
                    )
                else:
                    compressed_st.append(s)
            compressed_context["st"] = compressed_st

        # 2. Compress discovery facts if present
        if "disc" in serialized_context and isinstance(serialized_context["disc"], list):
            compressed_disc = []
            for item in serialized_context["disc"]:
                if isinstance(item, list) and len(item) == 2:
                    kind_id, facts = item
                    compressed_facts = []
                    if isinstance(facts, list):
                        for fact in facts:
                            if isinstance(fact, str) and len(fact) > 20:
                                compressed_facts.append(
                                    self.compress(fact, target_rate=target_rate, force_tokens=force_tokens)
                                )
                            else:
                                compressed_facts.append(fact)
                        compressed_disc.append([kind_id, compressed_facts])
                    else:
                        compressed_disc.append(item)
                else:
                    compressed_disc.append(item)
            compressed_context["disc"] = compressed_disc

        return compressed_context
