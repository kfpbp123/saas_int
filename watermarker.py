from PIL import Image
import os
import config

def add_watermark(input_image_path, output_image_path):
    """
    Накладывает логотип logo.png на изображение.
    Размер логотипа всегда пропорционален ширине основного фото (динамический размер).
    """
    try:
        if not os.path.exists(input_image_path):
            return False

        base_image = Image.open(input_image_path).convert("RGBA")
        width, height = base_image.size

        logo_path = "logo.png" 
        # Если нет logo.png, пробуем logo_original.png
        if not os.path.exists(logo_path):
            logo_path = "logo_original.png"

        if not os.path.exists(logo_path):
            print(f"⚠️ Логотип не найден. Сохраняю оригинал.")
            base_image.convert("RGB").save(output_image_path, "JPEG", quality=95)
            return True

        logo = Image.open(logo_path).convert("RGBA")
        
        # --- УМНОЕ МАСШТАБИРОВАНИЕ ---
        # Сделаем логотип заметнее - 35% от ширины
        target_width = int(width * 0.35)
        
        # Ограничения
        min_logo_width = max(150, int(width * 0.20))
        max_logo_width = int(width * 0.50)
        target_width = max(min_logo_width, min(target_width, max_logo_width))
        
        # Сохраняем пропорции логотипа
        w_percent = (target_width / float(logo.size[0]))
        target_height = int((float(logo.size[1]) * float(w_percent)))
        
        # Ресайз
        logo = logo.resize((target_width, target_height), Image.Resampling.LANCZOS)

        # --- ПОЗИЦИОНИРОВАНИЕ ---
        # По центру с небольшим смещением вниз для лучшей видимости
        position = ((width - target_width) // 2, (height - target_height) // 2 + int(height * 0.1))

        # Наложение через прозрачный слой (увеличим прозрачность логотипа если нужно, но PIL paste использует mask)
        overlay = Image.new("RGBA", base_image.size, (0, 0, 0, 0))
        overlay.paste(logo, position, mask=logo)
        
        combined = Image.alpha_composite(base_image, overlay)
        
        # Сохранение в JPEG
        combined.convert("RGB").save(output_image_path, "JPEG", quality=95, optimize=True)
        print(f"✅ [Watermark] Applied at {position}. Size: {target_width}x{target_height}")
        return True

    except Exception as e:
        print(f"❌ Watermarker error: {e}")
        try:
            Image.open(input_image_path).convert("RGB").save(output_image_path, "JPEG", quality=90)
        except: pass
        return False
