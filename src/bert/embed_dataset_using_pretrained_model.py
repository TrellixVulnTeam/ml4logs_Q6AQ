from datasets import load_dataset
from typing import List, Union, Dict, Optional
import torch
from pathlib import Path
from transformers import AutoTokenizer
from pathlib import Path
import time

from dataset_utils import remove_timestamp
from encoders import DistilBertForClsEmbedding

def encode_dataset(examples, tokenizer, encoder, device="cpu"):
    with torch.no_grad():
        embedding = encoder(**tokenizer(examples['text'],
                                        return_tensors='pt',
                                        truncation=True,
                                        padding=True).to(device)
                            ).embedding.cpu().detach().numpy().tolist()
    return {'embedding': embedding}


def embed_dataset(config):
    assert config.model_path is not None, "Model path must be specified!"
    assert config.input_dataset_log_file is not None, "Input dataset must be specified!"
    assert config.output_parent_folder is not None, "Output parent folder must be specified!"

    dataset_path = Path(config.input_dataset_log_file)
    dataset_name = f'{dataset_path.stem}/embedding_from_{Path(config.model_path).stem}' if config.dataset_output_name is None else config.dataset_output_name
    output_path = Path(config.output_parent_folder) / dataset_name
    assert (not output_path.exists()) or (output_path.exists() and output_path.is_dir() and not any(output_path.iterdir())), f"Output path {output_path} is not empty, can't create dataset"
    print(dataset_name)
    print(config)

    print(f"Loading dataset from {dataset_path}")
    start = time.time()
    dataset = load_dataset('text', data_files=str(dataset_path), split='train')
    print(f'Done, time taken: {time.time() - start}s')

    if config.remove_hdfs1_timestamp:
        print("Removing timestamps")
        start = time.time()
        cleaned_dataset = dataset.map(remove_timestamp, num_proc=config.threads)
        print(f'Done, time taken: {time.time() - start}s')
    else:
        cleaned_dataset = dataset

    print(f"Embedding dataset using batch size {config.batch_size} with model from {config.model_path}")
    start = time.time()
    tokenizer = AutoTokenizer.from_pretrained(config.base_model_name)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    encoder_model = DistilBertForClsEmbedding.from_pretrained(config.model_path).to(device)

    encoder_model.eval()
    embedded_dataset = cleaned_dataset.map(encode_dataset,
                                       fn_kwargs={'tokenizer': tokenizer,
                                                  'encoder': encoder_model,
                                                  'device': device},
                                       batched=True,
                                       batch_size=config.batch_size)
    print(f'Done, time taken: {time.time() - start}s')
    print(f"Saving dataset to {output_path}")
    start = time.time()
    embedded_dataset.save_to_disk(output_path)
    print(f'Done, time taken: {time.time() - start}s')


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Embedding of dataset using pretrained distilbert model")
    parser.add_argument('--model-path', default=None, type=str, help="Path to folder containing the pretrained DistilBertForClsEmbedding model")
    parser.add_argument('--base-model-name', default="distilbert-base-cased", type=str, help="Name of the original model for selection of the correct Tokenizer")
    parser.add_argument("--dataset-output-name", default=None, type=str, help="Name of the dataset, will be used as folder name into the specified parent directory, if left empty will be generated from input name")
    parser.add_argument("--output-parent-folder", default=None, type=str, help="Dataset will be saved into a new directory in this folder, using either the provided --dataset-output-name or autogenerated name")
    parser.add_argument("--input-dataset-log-file", default=None, type=str)
    parser.add_argument("--batch-size", default=256, type=int)
    parser.add_argument('--remove-hdfs1-timestamp', default=False, action='store_true', help="Use TwoTowerICT")
    parser.add_argument("--threads", default=1, type=int)

    config = parser.parse_args()
    embed_dataset(config)


if __name__ == '__main__':
    start = time.time()
    main()
    end = time.time()
    print(f'Total time taken: {end - start}s')