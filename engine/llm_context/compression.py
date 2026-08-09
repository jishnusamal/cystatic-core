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

        # 2. Compress symbols 'sym' if present
        if "sym" in serialized_context and isinstance(serialized_context["sym"], list):
            compressed_sym: list[Any] = []
            for item in serialized_context["sym"]:
                if isinstance(item, (list, tuple)):
                    compressed_item: list[Any] = []
                    for elem in item:
                        if isinstance(elem, str) and len(elem) > 20:
                            compressed_item.append(
                                self.compress(elem, target_rate=target_rate, force_tokens=force_tokens)
                            )
                        else:
                            compressed_item.append(elem)
                    compressed_sym.append(type(item)(compressed_item))
                elif isinstance(item, str) and len(item) > 20:
                    compressed_sym.append(
                        self.compress(item, target_rate=target_rate, force_tokens=force_tokens)
                    )
                else:
                    compressed_sym.append(item)
            compressed_context["sym"] = compressed_sym

        # 3. Compress execution graph 'eg' if present
        if "eg" in serialized_context and isinstance(serialized_context["eg"], dict):
            compressed_eg = dict(serialized_context["eg"])
            for eg_key in ("nodes", "edges"):
                if eg_key in compressed_eg and isinstance(compressed_eg[eg_key], list):
                    compressed_nodes: list[Any] = []
                    for node in compressed_eg[eg_key]:
                        if isinstance(node, (list, tuple)):
                            compressed_node: list[Any] = []
                            for elem in node:
                                if isinstance(elem, str) and len(elem) > 20:
                                    compressed_node.append(
                                        self.compress(elem, target_rate=target_rate, force_tokens=force_tokens)
                                    )
                                else:
                                    compressed_node.append(elem)
                            compressed_nodes.append(type(node)(compressed_node))
                        elif isinstance(node, str) and len(node) > 20:
                            compressed_nodes.append(
                                self.compress(node, target_rate=target_rate, force_tokens=force_tokens)
                            )
                        else:
                            compressed_nodes.append(node)
                    compressed_eg[eg_key] = compressed_nodes
            compressed_context["eg"] = compressed_eg

        # 4. Compress file changes 'cf' if present
        if "cf" in serialized_context and isinstance(serialized_context["cf"], list):
            compressed_cf: list[Any] = []
            for item in serialized_context["cf"]:
                if isinstance(item, (list, tuple)):
                    compressed_cf_item: list[Any] = []
                    for elem in item:
                        if isinstance(elem, (list, tuple)):
                            compressed_sub: list[Any] = []
                            for sub in elem:
                                if isinstance(sub, str) and len(sub) > 20:
                                    compressed_sub.append(
                                        self.compress(sub, target_rate=target_rate, force_tokens=force_tokens)
                                    )
                                else:
                                    compressed_sub.append(sub)
                            compressed_cf_item.append(type(elem)(compressed_sub))
                        elif isinstance(elem, str) and len(elem) > 20:
                            compressed_cf_item.append(
                                self.compress(elem, target_rate=target_rate, force_tokens=force_tokens)
                            )
                        else:
                            compressed_cf_item.append(elem)
                    compressed_cf.append(type(item)(compressed_cf_item))
                elif isinstance(item, str) and len(item) > 20:
                    compressed_cf.append(
                        self.compress(item, target_rate=target_rate, force_tokens=force_tokens)
                    )
                else:
                    compressed_cf.append(item)
            compressed_context["cf"] = compressed_cf

        # 5. Compress discovery facts 'disc' if present
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
