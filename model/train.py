"""Entrena el SVD (Surprise), evalúa y precalcula el Top 10 por usuario (EP3, secc. 14).

Uso:  python model/train.py --data data --out artifacts
Salida en artifacts/: svd_model.pkl, metrics.json, shopfast.db (SQLite con recomendaciones)
"""
import argparse
import json
import pickle
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from surprise import SVD, Dataset, Reader, accuracy

SEED, TEST_SIZE, K, REL_THRESHOLD = 42, 0.20, 10, 4   # relevante = carrito o compra (>= 4)
N_FACTORS, N_EPOCHS = 50, 20
COLD_USERS = ["U_COLD01", "U_COLD02", "U_COLD03"]


def main(data: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    products = pd.read_csv(data / "products.csv")
    inter = pd.read_csv(data / "interactions.csv")

    # División 80/20 sin solapamiento (los pares usuario-producto ya son únicos)
    test_df = inter.sample(frac=TEST_SIZE, random_state=SEED)
    train_df = inter.drop(test_df.index)

    trainset = Dataset.load_from_df(train_df[["user_id", "product_id", "rating"]],
                                    Reader(rating_scale=(1, 5))).build_full_trainset()
    algo = SVD(n_factors=N_FACTORS, n_epochs=N_EPOCHS, random_state=SEED)
    algo.fit(trainset)

    # --- RMSE / MAE sobre el conjunto de prueba ---
    triples = list(test_df[["user_id", "product_id", "rating"]].itertuples(index=False, name=None))
    preds = algo.test(triples)
    rmse, mae = accuracy.rmse(preds, verbose=False), accuracy.mae(preds, verbose=False)

    # --- Puntajes para TODO el catálogo, vectorizado (no se usa predict() en línea) ---
    uids = [trainset.to_raw_uid(i) for i in range(trainset.n_users)]
    col_pids, cols = [], []
    for p in products.product_id:
        try:
            cols.append(trainset.to_inner_iid(p)); col_pids.append(p)
        except ValueError:          # producto sin interacciones en entrenamiento
            pass
    col_of = {p: j for j, p in enumerate(col_pids)}
    qi = algo.qi[cols]
    scores = np.clip(trainset.global_mean + algo.bu[:, None] + algo.bi[cols][None, :]
                     + algo.pu @ qi.T, 1, 5)
    qn = qi / (np.linalg.norm(qi, axis=1, keepdims=True) + 1e-9)   # coseno para explicaciones

    seen = train_df.groupby("user_id").product_id.apply(set).to_dict()
    relevant = (test_df[test_df.rating >= REL_THRESHOLD]
                .groupby("user_id").product_id.apply(set).to_dict())
    hist = {u: g for u, g in train_df.groupby("user_id")}
    cat = products.set_index("product_id").category.to_dict()
    name = products.set_index("product_id").name.to_dict()
    popularity = train_df.groupby("product_id").size().sort_values(ascending=False)

    top_rows, precs, recs = [], [], []
    for ui, uid in enumerate(uids):
        mask = np.array([p in seen.get(uid, ()) for p in col_pids])
        s = np.where(mask, -np.inf, scores[ui])
        order = np.argsort(-s)[:K]

        # Explicación (14.4): categoría frecuente / similitud con producto previo / populares
        h = hist.get(uid)
        fav_cat = h.category.value_counts().index[0] if h is not None else None
        strong = ([col_of[p] for p in h[h.rating >= REL_THRESHOLD].product_id if p in col_of]
                  if h is not None else [])
        for rank, j in enumerate(order, 1):
            pid = col_pids[j]
            if cat[pid] == fav_cat:
                reason = f"Coincide con tu categoría frecuente: {fav_cat}"
            elif strong:
                ref = strong[int(np.argmax(qn[strong] @ qn[j]))]
                reason = f"Similar a «{name[col_pids[ref]]}», que ya te interesó"
            else:
                reason = "Popular entre usuarios con patrones similares"
            top_rows.append((uid, rank, pid, round(float(s[j]), 3), reason))

        rel = relevant.get(uid, set())
        if rel:
            hits = len(rel & {col_pids[j] for j in order})
            precs.append(hits / K)
            recs.append(hits / len(rel))

    p_k, r_k = float(np.mean(precs)), float(np.mean(recs))
    f1 = 2 * p_k * r_k / (p_k + r_k) if (p_k + r_k) else 0.0
    metrics = {"rmse": round(rmse, 4), "mae": round(mae, 4),
               f"precision@{K}": round(p_k, 4), f"recall@{K}": round(r_k, 4),
               f"f1@{K}": round(f1, 4), "n_train": len(train_df), "n_test": len(test_df),
               "split": "80/20", "relevance_threshold": REL_THRESHOLD,
               "n_factors": N_FACTORS, "n_epochs": N_EPOCHS, "seed": SEED,
               "model_version": "svd-v1"}
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
    with open(out / "svd_model.pkl", "wb") as f:
        pickle.dump(algo, f)

    # --- SQLite: usuarios, productos, interacciones, recomendaciones, popularidad ---
    db = out / "shopfast.db"
    db.unlink(missing_ok=True)
    con = sqlite3.connect(db)
    users = pd.read_csv(data / "users.csv")
    # Usuarios de prueba SIN historial (caso de prueba 4: fallback por popularidad)
    cold = pd.DataFrame({"user_id": COLD_USERS})
    pd.concat([users, cold], ignore_index=True).to_sql("users", con, index=False)
    products.to_sql("products", con, index=False)
    inter.to_sql("interactions", con, index=False)
    pd.DataFrame(top_rows, columns=["user_id", "rank", "product_id", "predicted_rating",
                                    "reason"]).to_sql("recommendations", con, index=False)
    popularity.rename("n").reset_index().to_sql("popularity", con, index=False)
    con.execute("CREATE INDEX idx_rec_user ON recommendations(user_id, rank)")
    con.execute("CREATE INDEX idx_int_user ON interactions(user_id)")
    con.commit(); con.close()
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data", type=Path)
    ap.add_argument("--out", default="artifacts", type=Path)
    a = ap.parse_args()
    main(a.data, a.out)
