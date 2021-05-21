import os
from datasets import load_from_disk
from transformers import AutoTokenizer, Trainer, TrainingArguments
from ict import DataCollatorForPreprocessedICT, OneTowerICT, TwoTowerICT
import torch
from pathlib import Path

from dataset_utils import my_caching_load_from_disk

from encoders import KNOWN_ENCODER_CLASSES

def get_run_name(two_tower: bool,
                 fp16: bool,
                 dataset_name: str,
                 seed: int,
                 target_max_seq_len: int,
                 context_max_seq_len: int,
                 train_batch_size: int,
                 eval_batch_size: int,
                 output_encode_dim: int,
                 encoder_type: str,
                 pretrained_checkpoint: str):
    return f'{encoder_type} {pretrained_checkpoint} {"2T" if two_tower else "1T"}{" fp16" if fp16 else ""} {dataset_name} Seed-{seed} T-len {target_max_seq_len} C-len {context_max_seq_len} Tr-batch {train_batch_size} Ev-b {eval_batch_size} O-dim {output_encode_dim}'


def run_experiment(config):
    os.environ["WANDB_PROJECT"] = f"ICT" if config.wandb_project is None else config.wandb_project
    assert config.dataset_name is not None, "Dataset name must be filled"
    assert config.encoder_type in KNOWN_ENCODER_CLASSES, f"Encoder type must be one of valid options, which are [{','.join(list(KNOWN_ENCODER_CLASSES.keys()))}]"
    RUN_NAME = get_run_name(two_tower=config.two_tower,
                 fp16=config.fp16,
                 dataset_name=config.dataset_name,
                 seed=config.seed,
                 target_max_seq_len=config.target_max_seq_len,
                 context_max_seq_len=config.context_max_seq_len,
                 train_batch_size=config.train_batch_size,
                 eval_batch_size=config.eval_batch_size,
                 output_encode_dim=config.output_encode_dim,
                 encoder_type=config.encoder_type,
                 pretrained_checkpoint=config.bert_model)
    print(RUN_NAME)
    tokenizer = AutoTokenizer.from_pretrained(config.bert_model, use_fast=True)
    data_collator = DataCollatorForPreprocessedICT(target_max_seq=config.target_max_seq_len,
                                                   context_max_seq=config.context_max_seq_len,
                                                   pad_token=tokenizer.pad_token_id,
                                                   start_token=tokenizer.cls_token_id,
                                                   sep_token=tokenizer.sep_token_id)

    assert config.train_dataset is not None, "Train dataset must not be None"
    assert config.eval_dataset is not None, "Eval dataset must not be None"

    train_dataset = my_caching_load_from_disk(Path(config.train_dataset))
    eval_dataset = my_caching_load_from_disk(Path(config.eval_dataset))

    tower_class = KNOWN_ENCODER_CLASSES[config.encoder_type]

    model = TwoTowerICT(tower_class, config.bert_model, output_encode_dimension=config.output_encode_dim) if config.two_tower else OneTowerICT(tower_class, config.bert_model, output_encode_dimension=config.output_encode_dim)
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model = model.to(device)

    training_args = TrainingArguments(output_dir=f"../../models/ICT/{RUN_NAME.replace(' ', '_')}",
                                      fp16=config.fp16,
                                      num_train_epochs=config.epochs,
                                      per_device_eval_batch_size=config.eval_batch_size, 
                                      per_device_train_batch_size=config.train_batch_size,
                                      warmup_steps=1000,                # number of warmup steps for learning rate scheduler
                                      weight_decay=0.01,               # strength of weight decay
                                      logging_dir='../../logs',            # directory for storing logs
                                      logging_steps=config.logging_steps,
                                      logging_first_step=True,
                                      eval_steps=config.eval_steps,
                                      evaluation_strategy='steps',
                                      prediction_loss_only=True,
                                      save_steps=config.save_steps,
                                      save_total_limit=config.save_total_limit,
                                      dataloader_drop_last=True,
                                      label_names=['target', 'context'],
                                      seed=config.seed,
                                      run_name=RUN_NAME,
                                      remove_unused_columns=False)

    trainer = Trainer(model=model,
                      args=training_args,
                      data_collator=data_collator,
                      train_dataset=train_dataset,
                      eval_dataset=eval_dataset
                      )

    trainer.train(resume_from_checkpoint=config.checkpoint_directory)
    trainer.save_model()
    model.save_encoder(RUN_NAME.replace(' ', '_'), Path('../../models/encoders'))
    

def main():
    print("Running in main func")
    import argparse
    parser = argparse.ArgumentParser(description="Runner for ICT experiments")
    parser.add_argument('--two-tower', default=0, type=int, help="Use TwoTowerICT, use int values, 0 for false, 1 for true")
    parser.add_argument('--fp16', default=False, action='store_true', help="Use half-precision")
    parser.add_argument('--bert-model', default="distilbert-base-cased", type=str, help="Pretrained Transformer for the encoder towers. Carefully set to compatible value with --encoder-type")
    parser.add_argument('--encoder-type', default="DistilbertCls", type=str, help=f"Encoder tower type, set to one of [{','.join(list(KNOWN_ENCODER_CLASSES.keys()))}]")
    parser.add_argument("--train-batch-size", default=64, type=int)
    parser.add_argument("--epochs", default=1, type=int)
    parser.add_argument("--logging-steps", default=10, type=int)
    parser.add_argument("--eval-steps", default=500, type=int)
    parser.add_argument("--save-steps", default=500, type=int)
    parser.add_argument("--save-total-limit", default=25, type=int)
    parser.add_argument("--eval-batch-size", default=64, type=int)
    parser.add_argument("--target-max-seq-len", default=512, type=int)
    parser.add_argument("--context-max-seq-len", default=512, type=int)
    parser.add_argument("--output-encode-dim", default=100, type=int, help="Output dimension for the encoder towers")
    parser.add_argument("--checkpoint-directory", default=None, type=str, help="Directory of checkpoint for resuming training")
    parser.add_argument("--seed", default=42, type=int)
    parser.add_argument("--dataset-name", default=None, type=str)
    parser.add_argument("--train-dataset", default=None, type=str, help="Directory containing the preprocessed training dataset")
    parser.add_argument("--eval-dataset", default=None, type=str, help="Directory containing the preprocessed training dataset")
    parser.add_argument("--wandb-project", default=None, type=str)

    config = parser.parse_args()
    run_experiment(config)


if __name__ == '__main__':
    print("Running in if name main")
    main()