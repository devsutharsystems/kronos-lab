"""Per-sample Kronos forecasting.

Adapted from Kronos (https://github.com/shiyu-coder/Kronos), model/kronos.py,
functions ``auto_regressive_inference`` and ``KronosPredictor.predict_batch``.
Kronos is MIT licensed, Copyright (c) 2025 ShiYu; see third_party/KRONOS_LICENSE.

What differs from the original: NOTHING in the sampling logic. The token loop is
copied statement for statement (pinned commit in third_party/KRONOS_PIN.md). The
only changes are
  1. the function returns the per-sample decoded paths instead of
     ``np.mean(preds, axis=1)``, and
  2. the normalisation inverse is applied to each sample path before returning.
Sampling primitives (``sample_from_logits``, ``calc_time_stamps``) are imported
from third_party, not re-implemented. third_party is never edited.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

KRONOS_DIR = Path(__file__).resolve().parent.parent / "third_party" / "kronos"
if str(KRONOS_DIR) not in sys.path:
    sys.path.insert(0, str(KRONOS_DIR))

from model.kronos import calc_time_stamps, sample_from_logits  # noqa: E402

FEATURES = ["open", "high", "low", "close", "volume", "amount"]


def auto_regressive_samples(tokenizer, model, x, x_stamp, y_stamp, max_context, pred_len,
                            clip=5, T=1.0, top_k=0, top_p=0.99, sample_count=5, verbose=False):
    """Copy of Kronos ``auto_regressive_inference`` returning (B, S, L, F) before averaging.

    Output is in the normalised space of ``x``; L is the decoded context window length
    (the last ``pred_len`` positions are the forecast).
    """
    with torch.no_grad():
        x = torch.clip(x, -clip, clip)

        device = x.device
        x = x.unsqueeze(1).repeat(1, sample_count, 1, 1).reshape(-1, x.size(1), x.size(2)).to(device)
        x_stamp = x_stamp.unsqueeze(1).repeat(1, sample_count, 1, 1).reshape(-1, x_stamp.size(1), x_stamp.size(2)).to(device)
        y_stamp = y_stamp.unsqueeze(1).repeat(1, sample_count, 1, 1).reshape(-1, y_stamp.size(1), y_stamp.size(2)).to(device)

        x_token = tokenizer.encode(x, half=True)

        initial_seq_len = x.size(1)
        batch_size = x_token[0].size(0)
        total_seq_len = initial_seq_len + pred_len
        full_stamp = torch.cat([x_stamp, y_stamp], dim=1)

        generated_pre = x_token[0].new_empty(batch_size, pred_len)
        generated_post = x_token[1].new_empty(batch_size, pred_len)

        pre_buffer = x_token[0].new_zeros(batch_size, max_context)
        post_buffer = x_token[1].new_zeros(batch_size, max_context)
        buffer_len = min(initial_seq_len, max_context)
        if buffer_len > 0:
            start_idx = max(0, initial_seq_len - max_context)
            pre_buffer[:, :buffer_len] = x_token[0][:, start_idx:start_idx + buffer_len]
            post_buffer[:, :buffer_len] = x_token[1][:, start_idx:start_idx + buffer_len]

        for i in range(pred_len):
            current_seq_len = initial_seq_len + i
            window_len = min(current_seq_len, max_context)

            if current_seq_len <= max_context:
                input_tokens = [
                    pre_buffer[:, :window_len],
                    post_buffer[:, :window_len]
                ]
            else:
                input_tokens = [pre_buffer, post_buffer]

            context_end = current_seq_len
            context_start = max(0, context_end - max_context)
            current_stamp = full_stamp[:, context_start:context_end, :].contiguous()

            s1_logits, context = model.decode_s1(input_tokens[0], input_tokens[1], current_stamp)
            s1_logits = s1_logits[:, -1, :]
            sample_pre = sample_from_logits(s1_logits, temperature=T, top_k=top_k, top_p=top_p, sample_logits=True)

            s2_logits = model.decode_s2(context, sample_pre)
            s2_logits = s2_logits[:, -1, :]
            sample_post = sample_from_logits(s2_logits, temperature=T, top_k=top_k, top_p=top_p, sample_logits=True)

            generated_pre[:, i] = sample_pre.squeeze(-1)
            generated_post[:, i] = sample_post.squeeze(-1)

            if current_seq_len < max_context:
                pre_buffer[:, current_seq_len] = sample_pre.squeeze(-1)
                post_buffer[:, current_seq_len] = sample_post.squeeze(-1)
            else:
                pre_buffer.copy_(torch.roll(pre_buffer, shifts=-1, dims=1))
                post_buffer.copy_(torch.roll(post_buffer, shifts=-1, dims=1))
                pre_buffer[:, -1] = sample_pre.squeeze(-1)
                post_buffer[:, -1] = sample_post.squeeze(-1)

        full_pre = torch.cat([x_token[0], generated_pre], dim=1)
        full_post = torch.cat([x_token[1], generated_post], dim=1)

        context_start = max(0, total_seq_len - max_context)
        input_tokens = [
            full_pre[:, context_start:total_seq_len].contiguous(),
            full_post[:, context_start:total_seq_len].contiguous()
        ]
        z = tokenizer.decode(input_tokens, half=True)
        z = z.reshape(-1, sample_count, z.size(1), z.size(2))
        return z.cpu().numpy()  # original continues: np.mean(preds, axis=1)


def predict_samples(predictor, df_list, x_timestamp_list, y_timestamp_list, pred_len,
                    T=1.0, top_k=0, top_p=0.9, sample_count=1):
    """Like ``KronosPredictor.predict_batch`` but returns all sample paths in price space.

    Returns an array of shape (B, sample_count, pred_len, 6); columns are ``FEATURES``.
    Same normalisation as the original: mean/std of the context window only, clip ±predictor.clip.
    """
    p = predictor
    x_list, xs_list, ys_list, means, stds = [], [], [], [], []
    for df, xt, yt in zip(df_list, x_timestamp_list, y_timestamp_list):
        df = df.copy()
        if p.vol_col not in df.columns:
            df[p.vol_col] = 0.0
            df[p.amt_vol] = 0.0
        if p.amt_vol not in df.columns and p.vol_col in df.columns:
            df[p.amt_vol] = df[p.vol_col] * df[p.price_cols].mean(axis=1)
        if df[p.price_cols + [p.vol_col, p.amt_vol]].isnull().values.any():
            raise ValueError("Input DataFrame contains NaN values in price or volume columns.")
        x = df[p.price_cols + [p.vol_col, p.amt_vol]].values.astype(np.float32)
        x_stamp = calc_time_stamps(xt).values.astype(np.float32)
        y_stamp = calc_time_stamps(yt).values.astype(np.float32)
        if y_stamp.shape[0] != pred_len:
            raise ValueError(f"y_timestamp length should equal pred_len={pred_len}, got {y_stamp.shape[0]}.")
        x_mean, x_std = np.mean(x, axis=0), np.std(x, axis=0)
        x_norm = np.clip((x - x_mean) / (x_std + 1e-5), -p.clip, p.clip)
        x_list.append(x_norm); xs_list.append(x_stamp); ys_list.append(y_stamp)
        means.append(x_mean); stds.append(x_std)

    x_t = torch.from_numpy(np.stack(x_list).astype(np.float32)).to(p.device)
    xs_t = torch.from_numpy(np.stack(xs_list).astype(np.float32)).to(p.device)
    ys_t = torch.from_numpy(np.stack(ys_list).astype(np.float32)).to(p.device)

    z = auto_regressive_samples(p.tokenizer, p.model, x_t, xs_t, ys_t, p.max_context, pred_len,
                                p.clip, T, top_k, top_p, sample_count, False)
    z = z[:, :, -pred_len:, :]  # (B, S, pred_len, F), normalised space
    out = np.empty_like(z)
    for i in range(z.shape[0]):
        out[i] = z[i] * (stds[i] + 1e-5) + means[i]
    return out
