# Recall second brain

## The mental model

Karpathy's language-model work makes the learning loop concrete: data becomes tokens, tokens become context, and the model predicts the next useful piece of text. Recall applies the same idea at the application level:

1. You write a note. PostgreSQL stores it as the durable corpus.
2. A question is split into useful words and used to retrieve memories.
3. The retrieved memories become the model context.
4. Ollama generates an answer grounded in that context.
5. The question and answer are stored as conversation history.

## Data flow

```text
New note -> PostgreSQL wiki_notes table
                 |
Question -> PostgreSQL search -> build_prompt -> local model -> answer
                 |                              |
                 +-------- retrieved notes ----+ 
                                                  |
                                  PostgreSQL wiki_chats table
```

## Why this is a good first version

It keeps the important pieces visible and replaceable. You can later improve retrieval with embeddings, add your own tokenizer experiments, or fine-tune a model without changing the note editor or PostgreSQL schema.