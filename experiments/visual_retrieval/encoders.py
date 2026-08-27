"""Optional local image encoders used by the visual retrieval spike.

Imports for torch/open_clip are intentionally lazy.  The LumiMatch production
environment remains usable when the experimental environment is not installed.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

MODEL_SPECS: dict[str, dict[str, object]] = {
    "openclip_vit_b32": {
        "backend": "open_clip",
        "model_name": "ViT-B-32",
        "pretrained": "openai",
        "model_id": "openai/CLIP:ViT-B-32/openai",
        "text": True,
    },
    "mobileclip2_s0": {
        "backend": "open_clip",
        "model_name": "MobileCLIP2-S0",
        "pretrained": "dfndr2b",
        "model_id": "apple/ml-mobileclip:MobileCLIP2-S0/dfndr2b",
        "text": True,
    },
    "mobileclip2_s2": {
        "backend": "open_clip",
        "model_name": "MobileCLIP2-S2",
        "pretrained": "dfndr2b",
        "model_id": "apple/ml-mobileclip:MobileCLIP2-S2/dfndr2b",
        "text": True,
    },
    "dinov2_vits14": {
        "backend": "dinov2",
        "model_name": "dinov2_vits14",
        "pretrained": "facebookresearch/dinov2:dinov2_vits14",
        "model_id": "facebookresearch/dinov2:dinov2_vits14",
        "text": False,
    },
}


@dataclass
class Encoder:
    name: str
    spec: dict[str, object]
    torch: Any
    model: Any
    preprocess: Callable[[Image.Image], Any]
    tokenizer: Callable[[list[str]], Any] | None
    device: str
    load_seconds: float

    @property
    def supports_text(self) -> bool:
        return bool(self.spec.get("text")) and self.tokenizer is not None

    def encode_images(self, paths: list[Path], *, batch_size: int = 16) -> Any:
        import numpy as np

        outputs: list[Any] = []
        self.model.eval()
        with self.torch.inference_mode():
            for start in range(0, len(paths), max(1, batch_size)):
                batch_paths = paths[start : start + max(1, batch_size)]
                tensors = []
                for path in batch_paths:
                    with Image.open(path) as image:
                        tensors.append(self.preprocess(image.convert("RGB")))
                batch = self.torch.stack(tensors).to(self.device)
                if self.spec["backend"] == "open_clip":
                    features = self.model.encode_image(batch)
                else:
                    features = self.model(batch)
                    if isinstance(features, dict):
                        selected = features.get("x_norm_clstoken")
                        if selected is None:
                            selected = features.get("x_prenorm")
                        features = (
                            selected
                            if selected is not None
                            else next(iter(features.values()))
                        )
                        if getattr(features, "ndim", 0) == 3:
                            features = features[:, 0]
                features = features.float()
                features = features / features.norm(dim=-1, keepdim=True).clamp_min(
                    1e-12
                )
                outputs.append(
                    features.detach().cpu().numpy().astype(np.float32, copy=False)
                )
        if not outputs:
            return np.empty((0, 0), dtype=np.float32)
        return np.concatenate(outputs, axis=0)

    def encode_text(self, texts: list[str]) -> Any:
        if not self.supports_text or self.tokenizer is None:
            raise RuntimeError(f"{self.name} does not expose a shared image/text space")
        tokens = self.tokenizer(texts).to(self.device)
        with self.torch.inference_mode():
            features = self.model.encode_text(tokens)
            features = features.float()
            features = features / features.norm(dim=-1, keepdim=True).clamp_min(1e-12)
        return features.detach().cpu().numpy().astype("float32", copy=False)


def _dino_preprocess(torch: Any) -> Callable[[Image.Image], Any]:
    try:
        from torchvision import transforms

        return transforms.Compose(
            [
                transforms.Resize(
                    256, interpolation=transforms.InterpolationMode.BICUBIC
                ),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
            ]
        )
    except (ImportError, RuntimeError):
        import numpy as np

        def preprocess(image: Image.Image) -> Any:
            image = image.convert("RGB")
            image.thumbnail((256, 256), Image.Resampling.BICUBIC)
            canvas = Image.new("RGB", (256, 256), "white")
            canvas.paste(image, ((256 - image.width) // 2, (256 - image.height) // 2))
            canvas = canvas.crop((16, 16, 240, 240))
            array = np.asarray(canvas, dtype="float32") / 255.0
            array = (
                array - np.asarray((0.485, 0.456, 0.406), dtype="float32")
            ) / np.asarray((0.229, 0.224, 0.225), dtype="float32")
            return torch.from_numpy(array.transpose(2, 0, 1))

        return preprocess


def _configure_model_cache(model_cache: Path) -> None:
    model_cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TORCH_HOME", str(model_cache / "torch"))
    os.environ.setdefault("HF_HOME", str(model_cache / "huggingface"))
    os.environ.setdefault(
        "HUGGINGFACE_HUB_CACHE", str(model_cache / "huggingface" / "hub")
    )
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")


def load_encoder(
    name: str, *, model_cache: Path | None = None, threads: int | None = None
) -> Encoder:
    if name not in MODEL_SPECS:
        raise ValueError(
            f"unknown model {name!r}; choose from {', '.join(sorted(MODEL_SPECS))}"
        )
    spec = MODEL_SPECS[name]
    if model_cache:
        _configure_model_cache(model_cache)
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("torch is not installed in the visual environment") from exc
    if threads:
        torch.set_num_threads(max(1, threads))
    device = "cpu"
    started = time.monotonic()
    tokenizer: Callable[[list[str]], Any] | None = None
    if spec["backend"] == "open_clip":
        try:
            import open_clip
        except ImportError as exc:
            raise RuntimeError(
                "open_clip_torch is not installed in the visual environment"
            ) from exc
        model, _, preprocess = open_clip.create_model_and_transforms(
            str(spec["model_name"]), pretrained=str(spec["pretrained"]), device=device
        )
        tokenizer = open_clip.get_tokenizer(str(spec["model_name"]))
    else:
        torch.hub.set_dir(str((model_cache or Path.home() / ".cache") / "torch"))
        model = torch.hub.load(
            "facebookresearch/dinov2", str(spec["model_name"]), pretrained=True
        )
        preprocess = _dino_preprocess(torch)
    model.eval()
    return Encoder(
        name,
        spec,
        torch,
        model,
        preprocess,
        tokenizer,
        device,
        time.monotonic() - started,
    )


def model_metadata(
    encoder: Encoder, *, model_cache: Path | None = None
) -> dict[str, object]:
    parameter_bytes = 0
    for parameter in encoder.model.parameters():
        parameter_bytes += parameter.numel() * parameter.element_size()
    checkpoint_bytes = None
    if model_cache and model_cache.exists():
        total = 0
        for path in model_cache.rglob("*"):
            if path.is_file() and path.suffix.casefold() in {
                ".pt",
                ".pth",
                ".bin",
                ".safetensors",
            }:
                try:
                    total += path.stat().st_size
                except OSError:
                    pass
        checkpoint_bytes = total or None
    return {
        "model": encoder.name,
        "model_id": encoder.spec["model_id"],
        "model_name": encoder.spec["model_name"],
        "pretrained": encoder.spec["pretrained"],
        "backend": encoder.spec["backend"],
        "supports_text": encoder.supports_text,
        "load_seconds": round(encoder.load_seconds, 3),
        "parameter_size_mb": round(parameter_bytes / 1024**2, 2),
        "checkpoint_size_mb": round(checkpoint_bytes / 1024**2, 2)
        if checkpoint_bytes
        else None,
        "device": encoder.device,
    }


def write_model_failure(path: Path, model: str, error: BaseException) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "model": model,
                "status": "failed",
                "error": f"{type(error).__name__}: {error}",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
