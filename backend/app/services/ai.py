import asyncio
import base64
import io
from pathlib import Path
from typing import Any

from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

from app.core.config import get_settings
from app.schemas.domain import DraftImageGenerateRequest, ListingAutofillOutput


class AIService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = OpenAI(api_key=self.settings.openai_api_key) if self.settings.openai_api_key else None

    async def autofill_listing(
        self,
        image_paths: list[Path],
        currency_code: str,
        category_hint: str | None = None,
    ) -> tuple[ListingAutofillOutput, str]:
        if not self.client:
            return self._mock_autofill(image_paths, currency_code, category_hint), "mock-autofill"
        return await asyncio.to_thread(self._autofill_sync, image_paths, currency_code, category_hint)

    async def generate_sale_image(
        self,
        title: str,
        description: str,
        attributes: dict[str, Any],
        request: DraftImageGenerateRequest,
    ) -> tuple[bytes, dict[str, Any], int]:
        if not self.client:
            return self._mock_image(title, request.style_preset)
        return await asyncio.to_thread(self._generate_sale_image_sync, title, description, attributes, request)

    def _autofill_sync(
        self,
        image_paths: list[Path],
        currency_code: str,
        category_hint: str | None = None,
    ) -> tuple[ListingAutofillOutput, str]:
        payload = [
            {
                "type": "input_text",
                "text": (
                    "Return a structured listing suggestion for a used-item marketplace. "
                    "Use only facts visible in the photos. "
                    "If brand, exact size, or intended use cannot be supported from the photos, return null for those fields and include the field name in missing_fields. "
                    "Set condition_score on a 1-10 scale where 10 is close to new and 1 is heavily worn. "
                    "Use title as marketplace copy and product_name as the actual product name. "
                    "Do not invent model numbers, logos, exact dimensions, or condition details. "
                    f"Prefer prices in {currency_code}. "
                    f"Category hint: {category_hint or 'unknown'}."
                ),
            }
        ]
        for image_path in image_paths:
            encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
            payload.append(
                {
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{encoded}",
                    "detail": "high",
                }
            )

        try:
            response = self.client.responses.parse(
                model=self.settings.openai_autofill_model,
                input=[{"role": "user", "content": payload}],
                text_format=ListingAutofillOutput,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise ValueError("No structured output returned.")
            return parsed, self.settings.openai_autofill_model
        except Exception:
            fallback = self.client.responses.parse(
                model=self.settings.openai_autofill_fallback_model,
                input=[{"role": "user", "content": payload}],
                text_format=ListingAutofillOutput,
            )
            parsed = fallback.output_parsed
            if parsed is None:
                raise ValueError("No structured output returned from fallback model.")
            return parsed, self.settings.openai_autofill_fallback_model

    def _generate_sale_image_sync(
        self,
        title: str,
        description: str,
        attributes: dict[str, Any],
        request: DraftImageGenerateRequest,
    ) -> tuple[bytes, dict[str, Any], int]:
        prompt = (
            "Create a clean, premium resale marketplace image for a used product. "
            f"Title: {title}. Description: {description}. Attributes: {attributes}. "
            f"Style preset: {request.style_preset}. Show the item as a realistic product photo on a neutral background. "
            "Do not add price stickers, watermarks, or brand logos unless explicitly present in the item details."
        )
        result = self.client.images.generate(
            model=self.settings.openai_image_model,
            prompt=prompt,
            size=request.size,
            quality=request.quality,
            background=request.background,
        )
        image_data = result.data[0]
        image_bytes = base64.b64decode(image_data.b64_json)
        metadata = {
            "provider": "openai",
            "model": self.settings.openai_image_model,
            "revised_prompt": getattr(image_data, "revised_prompt", None),
        }
        return image_bytes, metadata, self._credits_for_quality(request.quality)

    def _mock_autofill(
        self,
        image_paths: list[Path],
        currency_code: str,
        category_hint: str | None,
    ) -> ListingAutofillOutput:
        stem = image_paths[0].stem.replace("-", " ").replace("_", " ").title() if image_paths else "Used Item"
        category = ["electronics"] if "phone" in stem.lower() or "camera" in stem.lower() else ["home"]
        title = stem if stem != "Used Item" else "Second-hand item bundle"
        return ListingAutofillOutput(
            title=title,
            product_name=title,
            description=f"Pre-filled from uploaded photos. {title} looks suitable for a quick resale listing.",
            category_path=category,
            condition="Used - Good",
            condition_score=7,
            brand=None,
            color="Mixed",
            approx_dimensions_text=None,
            intended_use=None,
            attributes={"autofill_mode": "mock", "photo_count": len(image_paths)},
            suggested_price=49.0,
            currency_code=currency_code,
            price_confidence=0.52,
            missing_fields=["brand", "approx_dimensions_text", "intended_use"],
            safety_flags=[],
        )

    def _mock_image(self, title: str, style_preset: str) -> tuple[bytes, dict[str, Any], int]:
        image = Image.new("RGB", (1024, 1024), color=(246, 241, 233))
        draw = ImageDraw.Draw(image)
        accent = (34, 51, 59)
        draw.rounded_rectangle((72, 72, 952, 952), radius=48, outline=accent, width=6)
        draw.text((110, 140), "AI Sale Image", fill=accent, font=ImageFont.load_default())
        draw.text((110, 220), title[:64], fill=accent, font=ImageFont.load_default())
        draw.text((110, 300), f"Style: {style_preset[:40]}", fill=accent, font=ImageFont.load_default())
        draw.rectangle((180, 420, 844, 860), outline=(180, 132, 89), width=8)
        draw.text((420, 635), "ITEM", fill=(180, 132, 89), font=ImageFont.load_default())
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue(), {"provider": "mock"}, self._credits_for_quality("medium")

    def _credits_for_quality(self, quality: str) -> int:
        return {"low": 4, "medium": 8, "high": 12, "auto": 8}.get(quality, 8)
