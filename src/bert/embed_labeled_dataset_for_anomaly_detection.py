from typing import List, Union, Dict, Optional
import torch
from pathlib import Path
from transformers import AutoTokenizer, AutoConfig
import time
import logging
import pandas as pd
import numpy as np
from tqdm import tqdm
import pickle
import os

from dataset_utils import load_hdfs1_log_file_grouped
from encoders import KNOWN_ENCODER_CLASSES

logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))

log = logging.getLogger(__name__)

def encode_batch(batch, tokenizer, encoder, device="cpu"):
    with torch.no_grad():
        embedding = encoder(**tokenizer(batch,
                                        return_tensors='pt',
                                        truncation=True,
                                        padding=True).to(device)
                            ).embedding.cpu().detach().numpy()
    return embedding


def embed_dataset(config):
    assert config.model_path is not None, "Model path must be specified!"
    assert config.input_dataset_log_file is not None, "Input dataset must be specified!"
    assert config.input_dataset_labels_csv is not None, "Input dataset labels must be specified!"
    assert config.output_parent_folder is not None, "Output parent folder must be specified!"

    dataset_path = Path(config.input_dataset_log_file)
    label_path = Path(config.input_dataset_labels_csv)
    dataset_name = f'{dataset_path.stem}/labeled_embedding_from_{Path(config.model_path).stem}' if config.dataset_output_name is None else config.dataset_output_name
    output_path = Path(config.output_parent_folder) / dataset_name
    assert (not output_path.exists()) or (output_path.exists() and output_path.is_dir() and not any(output_path.iterdir())), f"Output path {output_path} is not empty, can't create dataset"
    log.info(dataset_name)
    log.info(config)

    log.info(f"Loading dataset from {dataset_path}")
    start = time.time()
    dataset = load_hdfs1_log_file_grouped(dataset_path)
    labels_df = pd.read_csv(label_path, converters={'Label': lambda x: x == 'Anomaly'})
    log.info(f'Done, time taken: {time.time() - start}s')


    log.info(f"Embedding dataset with model from {config.model_path}")
    start = time.time()
    tokenizer = AutoTokenizer.from_pretrained(config.base_model_name)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    available_encoder_classes_dict = {c.__name__:c for c in KNOWN_ENCODER_CLASSES.values()}
    model_config = AutoConfig.from_pretrained(config.model_path)
    encoder_model_class = available_encoder_classes_dict[model_config.architectures[0]]  # TODO: check whether acceptable solution

    encoder_model = encoder_model_class.from_pretrained(config.model_path).to(device)
    encoder_model.eval()

    embedded_dataset = {block_id: encode_batch(block_lines, tokenizer, encoder_model, device=device) for block_id, block_lines in tqdm(dataset.items())}
    log.info(f'Done, time taken: {time.time() - start}s')
    log.info(f"Saving dataset to {output_path}")
    start = time.time()
    ordered_by_label = [embedded_dataset[block_id] for block_id in labels_df['BlockId']]
    output_path.mkdir(parents=True, exist_ok=True)
    X_path = output_path / 'X.pickle'
    y_path = output_path / 'y.npy'
    with X_path.open('wb') as f:
        pickle.dump(ordered_by_label, f)
    np.save(y_path, labels_df['Label'].to_numpy(dtype=np.int8))

    log.info(f'Done, time taken: {time.time() - start}s')


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Embedding of dataset using pretrained distilbert model")
    parser.add_argument('--model-path', default=None, type=str, help="Path to folder containing the pretrained DistilBertForClsEmbedding model")
    parser.add_argument('--base-model-name', default="distilbert-base-cased", type=str, help="Name of the original model for selection of the correct Tokenizer")
    parser.add_argument("--dataset-output-name", default=None, type=str, help="Name of the dataset, will be used as folder name into the specified parent directory, if left empty will be generated from input name")
    parser.add_argument("--output-parent-folder", default=None, type=str, help="Dataset will be saved into a new directory in this folder, using either the provided --dataset-output-name or autogenerated name")
    parser.add_argument("--input-dataset-log-file", default=None, type=str)
    parser.add_argument("--input-dataset-labels-csv", default=None, type=str)

    config = parser.parse_args()
    embed_dataset(config)


if __name__ == '__main__':
    start = time.time()
    main()
    end = time.time()
    log.info(f'Total time taken: {end - start}s')