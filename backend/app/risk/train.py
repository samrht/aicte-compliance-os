"""Retrain the risk model and export it: python -m app.risk.train"""
import json

from app.risk import MODEL_JSON, train

if __name__ == "__main__":
    data = train()
    MODEL_JSON.write_text(json.dumps(data))
    print(f"wrote {MODEL_JSON} (holdout AUC {data['auc']})")
