"""Keep PyTorch's Intel OpenMP runtime out of the LightGBM process."""
from __future__ import annotations

import json
import sys


def main():
    import torch
    from sentence_transformers import SentenceTransformer
    from parts_search.pipelines.retrieval import preprocess

    options=json.loads(sys.stdin.readline())
    torch.set_num_threads(2)
    try:
        model=SentenceTransformer(options['modelId'],revision=options['revision'],device='cpu',local_files_only=True)
    except OSError:
        model=SentenceTransformer(options['modelId'],revision=options['revision'],device='cpu')
    print(json.dumps({'ready':True}),flush=True)
    for line in sys.stdin:
        request=json.loads(line)
        vectors=model.encode([preprocess(t,request['kind']) for t in request['texts']],batch_size=16,
                             normalize_embeddings=True,show_progress_bar=False).tolist()
        print(json.dumps(vectors),flush=True)


if __name__=='__main__':
    main()
