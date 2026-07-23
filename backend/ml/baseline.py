
import numpy as np
from sklearn.metrics import roc_auc_score, brier_score_loss


def _auc(y_true, prob):
    if len(np.unique(y_true)) < 2:  # 片クラスのみだと AUC は未定義
        return float("nan")
    return float(roc_auc_score(y_true, prob))


def temp_metrics(pred, y_true):
    err = np.asarray(pred, float) - np.asarray(y_true, float)
    return {"MAE": float(np.nanmean(np.abs(err))),
            "RMSE": float(np.sqrt(np.nanmean(err ** 2)))}


def precip_metrics(prob, y_true):
    return {"AUC": _auc(y_true, prob),
            "Brier": float(brier_score_loss(y_true, prob))}
