"""Small nanoGPT-style decoder-only model for learning and local wiki experiments."""

import torch
import torch.nn as nn
from torch.nn import functional as F


class GPTConfig:
    vocab_size: int
    block_size: int = 256
    n_layer: int = 4
    n_head: int = 4
    n_embd: int = 128


class CausalSelfAttention(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.key = nn.Linear(config.n_embd, config.n_embd, bias=False)
        self.query = nn.Linear(config.n_embd, config.n_embd, bias=False)
        self.value = nn.Linear(config.n_embd, config.n_embd, bias=False)
        self.proj = nn.Linear(config.n_embd, config.n_embd)
        self.register_buffer("mask", torch.tril(torch.ones(config.block_size, config.block_size)).view(1, 1, config.block_size, config.block_size))
        self.n_head = config.n_head

    def forward(self, inputs):
        batch, tokens, channels = inputs.shape
        keys = self.key(inputs).view(batch, tokens, self.n_head, channels // self.n_head).transpose(1, 2)
        queries = self.query(inputs).view(batch, tokens, self.n_head, channels // self.n_head).transpose(1, 2)
        values = self.value(inputs).view(batch, tokens, self.n_head, channels // self.n_head).transpose(1, 2)
        attention = (queries @ keys.transpose(-2, -1)) * (keys.size(-1) ** -0.5)
        attention = attention.masked_fill(self.mask[:, :, :tokens, :tokens] == 0, float("-inf"))
        attention = F.softmax(attention, dim=-1)
        output = (attention @ values).transpose(1, 2).contiguous().view(batch, tokens, channels)
        return self.proj(output)


class Block(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.ln1 = nn.LayerNorm(config.n_embd)
        self.attention = CausalSelfAttention(config)
        self.ln2 = nn.LayerNorm(config.n_embd)
        self.mlp = nn.Sequential(nn.Linear(config.n_embd, 4 * config.n_embd), nn.GELU(), nn.Linear(4 * config.n_embd, config.n_embd))

    def forward(self, inputs):
        inputs = inputs + self.attention(self.ln1(inputs))
        return inputs + self.mlp(self.ln2(inputs))


class NanoGPT(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.token_embedding = nn.Embedding(config.vocab_size, config.n_embd)
        self.position_embedding = nn.Embedding(config.block_size, config.n_embd)
        self.blocks = nn.Sequential(*(Block(config) for _ in range(config.n_layer)))
        self.ln = nn.LayerNorm(config.n_embd)
        self.head = nn.Linear(config.n_embd, config.vocab_size, bias=False)

    def forward(self, inputs, targets=None):
        positions = torch.arange(inputs.size(1), device=inputs.device)
        hidden = self.token_embedding(inputs) + self.position_embedding(positions)
        logits = self.head(self.ln(self.blocks(hidden)))
        loss = None if targets is None else F.cross_entropy(logits.view(-1, logits.size(-1)), targets.view(-1))
        return logits, loss


def load_checkpoint(path="models/wiki_nanogpt.pt"):
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    config = GPTConfig()
    config.__dict__.update(checkpoint["config"])
    model = NanoGPT(config)
    model.load_state_dict(checkpoint["model"])
    return model, checkpoint["stoi"], checkpoint["itos"]


def generate(prompt, path="models/wiki_nanogpt.pt", max_new_tokens=160):
    model, stoi, itos = load_checkpoint(path)
    model.eval()
    tokens = torch.tensor([[stoi.get(character, 0) for character in prompt[-model.config.block_size:]]])
    with torch.no_grad():
        for _ in range(max_new_tokens):
            context = tokens[:, -model.config.block_size:]
            logits, _ = model(context)
            next_token = torch.argmax(logits[:, -1, :], dim=-1, keepdim=True)
            tokens = torch.cat((tokens, next_token), dim=1)
    return "".join(itos[int(token)] for token in tokens[0])
