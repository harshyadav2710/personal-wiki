"""Train the small Karpathy-style GPT on the local wiki corpus."""

from pathlib import Path

import torch

from karpathy_nanogpt import GPTConfig, NanoGPT


ROOT = Path("source_files")
OUTPUT = Path("models/wiki_nanogpt.pt")


def train(steps=500):
    text = "\n\n".join(path.read_text(encoding="utf-8") for path in sorted(ROOT.rglob("*.md")))
    characters = sorted(set(text))
    stoi = {character: index for index, character in enumerate(characters)}
    itos = {index: character for character, index in stoi.items()}
    data = torch.tensor([stoi[character] for character in text], dtype=torch.long)
    config = GPTConfig()
    config.vocab_size = len(characters)
    model = NanoGPT(config)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4)
    torch.manual_seed(42)
    model.train()
    for step in range(steps):
        starts = torch.randint(0, len(data) - config.block_size - 1, (16,))
        inputs = torch.stack([data[start:start + config.block_size] for start in starts])
        targets = torch.stack([data[start + 1:start + config.block_size + 1] for start in starts])
        _, loss = model(inputs, targets)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        if step % 50 == 0:
            print(f"step={step} loss={loss.item():.4f}", flush=True)
    OUTPUT.parent.mkdir(exist_ok=True)
    torch.save({"config": config.__dict__, "stoi": stoi, "itos": itos, "model": model.state_dict()}, OUTPUT)
    print(f"Saved {OUTPUT}")


if __name__ == "__main__":
    train()
