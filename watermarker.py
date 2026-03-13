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
        # Логотип должен занимать примерно 25% от ширины изображения
        # Но не меньше 150 пикселей для читаемости на больших фото
        target_width = int(width * 0.25)
        
        # Ограничения: не слишком маленький на 4K и не слишком большой на 480p
        min_logo_width = max(120, int(width * 0.15))
        max_logo_width = int(width * 0.40)
        target_width = max(min_logo_width, min(target_width, max_logo_width))
        
        # Сохраняем пропорции логотипа
        w_percent = (target_width / float(logo.size[0]))
        target_height = int((float(logo.size[1]) * float(w_percent)))
        
        # Ресайз с высоким качеством
        logo = logo.resize((target_width, target_height), Image.Resampling.LANCZOS)

        # --- ПОЗИЦИОНИРОВАНИЕ ---
        # Отступ 4% от краев (динамический отступ)
        padding_x = int(width * 0.04)
        padding_y = int(height * 0.04)
        
        # Правый нижний угол
        position = (width - target_width - padding_x, height - target_height - padding_y)

        # Наложение через прозрачный слой
        overlay = Image.new("RGBA", base_image.size, (0, 0, 0, 0))
        overlay.paste(logo, position, mask=logo)
        
        combined = Image.alpha_composite(base_image, overlay)
        
        # Сохранение в JPEG с высоким качеством
        combined.convert("RGB").save(output_image_path, "JPEG", quality=95, optimize=True)
        print(f"✅ [Watermark] Photo: {width}x{height} | Logo width: {target_width}px")
        return True

    except Exception as e:
        print(f"❌ Watermarker error: {e}")
        # В случае ошибки просто копируем оригинал
        try:
            Image.open(input_image_path).convert("RGB").save(output_image_path, "JPEG", quality=90)
        except: pass
        return False
