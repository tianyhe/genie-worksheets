from typing import Tuple

import tiktoken

INSTRUCTION_START = "<|startofinstruction|>"
INSTRUCTION_END = "<|endofinstruction|>"
PROMPT_START = "<|startofinput|>"
PROMPT_END = "<|endofinput|>"


def load_prompt(prompt_file: str) -> Tuple[str, str]:
    with open(prompt_file, "r") as f:
        text = f.read()
        system_prompt = (
            text.split(INSTRUCTION_START)[1].split(INSTRUCTION_END)[0].strip()
        )
        prompt = text.split(PROMPT_START)[1].split(PROMPT_END)[0].strip()

    return system_prompt, prompt


def deep_compare_lists(list1, list2):
    try:
        # First, try the simple Counter method for hashable elements.
        from collections import Counter

        return Counter(list1) == Counter(list2)
    except TypeError:
        # If elements are unhashable, fall back to a method that sorts them.
        # This requires all elements to be comparable.
        try:
            return sorted(list1) == sorted(list2)
        except TypeError:
            # Final fallback: Convert inner structures to tuples if they are lists
            def to_tuple(x):
                if isinstance(x, list):
                    return tuple(to_tuple(e) for e in x)
                return x

            return sorted(map(to_tuple, list1)) == sorted(map(to_tuple, list2))


def extract_code_block_from_output(output: str, lang="python"):
    code = output.split("```")
    if len(code) > 1:
        res = code[1]
        if res.startswith(lang):
            res = res[len(lang) :]
        return res
    else:
        return output


def num_tokens_from_string(string: str, model: str = "gpt-3.5-turbo") -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.encoding_for_model(model)
    num_tokens = len(encoding.encode(string))
    return num_tokens
