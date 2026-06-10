import os
import sys
import logging
import torch
from transformers import (
    AutoProcessor,
    Qwen2VLForConditionalGeneration,
    BitsAndBytesConfig,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("model_test")


def test_load():
    repo = "Qwen/Qwen2.5-VL-7B-Instruct"
    logger.info(f"Testing load of {repo} with 4-bit quantization...")

    try:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )

        model = Qwen2VLForConditionalGeneration.from_pretrained(
            repo,
            quantization_config=bnb_config,
            device_map="auto",
            attn_implementation="flash_attention_2",
            trust_remote_code=True,
        )
        logger.info("Model loaded successfully!")

        processor = AutoProcessor.from_pretrained(repo, trust_remote_code=True)
        logger.info("Processor loaded successfully!")

    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_load()
