import openai
from transformers import AutoTokenizer
from concurrent.futures import ThreadPoolExecutor

########################
## Original note (kept for reference): "vllm automatically add <BoS> for some specific models (e.g., deepseek-ai's distill models), we need to avoid duplicated <BoS> tokens https://github.com/vllm-project/vllm/issues/9519"
## CORRECTION (verified 2026-07-30 via /tokenize on this server, vllm 0.25.1):
## vLLM does NOT auto-add BOS for these DeepSeek distills -- their tokenizers
## have add_bos_token=False (Qwen AND Llama), and add_special_tokens True/False
## both yield no BOS. So the Qwen templates below intentionally carry no BOS and
## get none. The Llama-8B template (further down) must add its own BOS because
## that model is BOS-sensitive; see the detailed note there.
########################
# Define a mapping of model names to their corresponding prompt templates
MODEL_TEMPLATES = {
    model: lambda p: "<｜User｜>" + p + "<｜Assistant｜>"
    for model in [
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
    ]
}

# vLLM 0.26+ does not auto-add BOS for the Llama tokenizer, so we must
# prepend it manually. Without BOS, the Llama distill model produces
# garbled output from the first token. See smoke_audit for evidence.
MODEL_TEMPLATES["deepseek-ai/DeepSeek-R1-Distill-Llama-8B"] = (
    lambda p: "<｜begin▁of▁sentence｜><｜User｜>" + p + "<｜Assistant｜>ILL\n"
)

MODEL_TEMPLATES.update(
    {
        # This Llama-based distill needs an EXPLICIT BOS. Note vLLM adds no
        # BOS for ANY of these distills -- add_bos_token=False for the Qwen
        # ones too, and /tokenize returns no BOS whether add_special_tokens
        # is True or False (so the top-of-file "vllm auto-adds BOS" note is
        # inaccurate for these models). The asymmetry is model sensitivity,
        # not tokenization: the Qwen distills stay coherent without a BOS,
        # but this Llama distill emits garbage from token 1 without it
        # (Llama-family models are highly BOS-sensitive). The explicit BOS
        # yields exactly one BOS token -- verified via /tokenize:
        # [128000(BOS), 128011(User), ...] (no double BOS). The "<think>\n"
        # cue starts reasoning, matching the DeepSeek-R1 template. End-to-end:
        # 87.9% on math500 with this template vs 0/500 without the BOS.
        model: lambda p: "<｜begin▁of▁sentence｜><｜User｜>" + p + "<｜Assistant｜><think>\n"
        for model in ["deepseek-ai/DeepSeek-R1-Distill-Llama-8B"]
    }
)

MODEL_TEMPLATES.update(
    {
        model: lambda p: (
            "<|im_start|>system\nPlease reason step by step, and put your final answer within \\boxed{}.<|im_end|>\n<|im_start|>user\n"
            + p
            + "<|im_end|>\n<|im_start|>assistant\n"
        )
        for model in ["Qwen/Qwen2.5-Math-7B-Instruct"]
    }
)

MODEL_TEMPLATES.update(
    {
        # Qwen3 reasoning models auto-emit <think>...</think> from a plain
        # ChatML assistant turn (no forced "reason step by step" system
        # prompt needed, unlike the non-reasoning Qwen2.5-Math template above).
        model: lambda p: "<|im_start|>user\n" + p + "<|im_end|>\n<|im_start|>assistant\n"
        for model in ["Qwen/Qwen3-8B", "Qwen/Qwen3-4B", "Qwen/Qwen3-14B", "Qwen/Qwen3-32B"]
    }
)


def apply_chat_template(prompt, model_name):
    # Get the template function for the model, default to identity function
    template_fn = MODEL_TEMPLATES.get(
        model_name, lambda p: "<｜User｜>" + p + "<｜Assistant｜>"
    )
    return template_fn(prompt)


class ClientModel:
    def __init__(self, model_name, url, api_key):
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url=url,
        )
        self.model_name = model_name

    def generate(self, prompt, max_tokens=2048, temperature=0.6, top_p=0.95, n=1):
        # print(f"Generating with model {self.model_name}")
        # print(f"Prompt: {prompt}")
        # print(f"Max tokens: {max_tokens}")
        # print(f"Temperature: {temperature}")
        # print(f"Top p: {top_p}")
        # print(f"N: {n}")
        # print("-"*100)
        completions = self.client.completions.create(
            model=self.model_name,
            prompt=prompt,
            echo=False,
            n=n,
            stream=False,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        )

        return completions

    def prepare_prompt(self, prompt):
        pass


class vllmClientModel(ClientModel):
    def __init__(self, model_name, url, api_key):
        super().__init__(model_name, url, api_key)
        self.model_name = model_name
        self.url = url
        self.api_key = api_key
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

    def generate_batch(
        self,
        prompts,
        max_tokens=2048,
        temperature=0.6,
        top_p=0.95,
        n=1,
        is_actives=None,
    ):
        def generate_completion(prompt, is_active, max_token):
            if is_active and max_token > 0:
                return self.client.completions.create(
                    model=self.model_name,
                    prompt=prompt,
                    echo=False,
                    n=n,
                    stream=False,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_token,
                    logprobs=2,
                )
            else:
                return None

        # Create a list to store completions in order
        completions = [None] * len(prompts)
        # Convert max_tokens to a list if it's not already
        if not isinstance(max_tokens, list):
            max_tokens = [max_tokens] * len(prompts)
        # Use ThreadPoolExecutor to parallelize requests while maintaining order
        with ThreadPoolExecutor() as executor:
            # Submit all tasks and store futures with their indices
            future_to_idx = {
                executor.submit(generate_completion, prompt, is_active, max_token): idx
                for idx, (prompt, is_active, max_token) in enumerate(
                    zip(prompts, is_actives, max_tokens)
                )
            }

            # As futures complete, store results in correct positions
            for future in future_to_idx:
                idx = future_to_idx[future]
                completions[idx] = future.result()

        return completions

    def generate_batch_probe(
        self,
        prompts,
        max_tokens=2048,
        temperature=0.6,
        top_p=0.95,
        n=1,
        is_actives=None,
    ):
        return self.generate_batch(
            prompts, max_tokens, temperature, top_p, n, is_actives
        )

    def prepare_prompt(self, prompt):
        chat_template = apply_chat_template(prompt, self.model_name)
        # print(chat_template)
        return chat_template
