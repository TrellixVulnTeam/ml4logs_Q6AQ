from transformers.file_utils import ModelOutput
from transformers import DistilBertModel, DistilBertPreTrainedModel
import torch
from dataclasses import dataclass


@dataclass
class EmbeddingOutput(ModelOutput):
    """
    ModelOutput class inspired per Huggingface Transformers library conventions, may be replaced by a suitable alternative class from the library if any exists.
    """
    embedding: torch.FloatTensor = None


class DistilBertForClsEmbedding(DistilBertPreTrainedModel):
    """
    DistilBertModel with a linear layer applied to [CLS] token.
    Initialize using .from_pretrained(path_or_model_name) method
    use task_specific_params={'cls_embedding_dimension': *YOUR EMBEDDING DIMENSION HERE*} to set embedding dimension
    """
    def __init__(self, config):
        super().__init__(config)
        if config.task_specific_params is None:
            config.task_specific_params = dict()

        self.distilbert = DistilBertModel(config)
        self.cls_projector = torch.nn.Linear(config.dim, config.task_specific_params.setdefault('cls_embedding_dimension', 512))

        self.init_weights()
    
    def forward(self, input_ids, attention_mask):
        bert_output = self.distilbert(input_ids=input_ids, attention_mask=attention_mask)
        cls_token_embedding = bert_output.last_hidden_state[:, 0]
        cls_encoding = self.cls_projector(cls_token_embedding)
        return EmbeddingOutput(embedding=cls_encoding)