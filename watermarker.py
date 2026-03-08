from PIL import Image
import os
import config

def add_watermark(input_image_path, output_image_path):
    """Накладывает логотип logo.png, масштабируя его под размер фото."""
    try:
        base_image = Image.open(input_image_path).convert("RGBA")
        width, height = base_image.size

        # Путь к вашему логотипу (убедитесь, что файл лежит в папке с ботом)
        logo_path = "logo.png" 
        if not os.path.exists(logo_path):
            print(f"⚠️ Файл {logo_path} не найден! Просто сохраняю фото.")
            base_image.convert("RGB").save(output_image_path, "JPEG", quality=95)
            return

        logo = Image.open(logo_path).convert("RGBA")
        
        # --- УМНОЕ МАСШТАБИРОВАНИЕ ---
        # Логотип всегда будет занимать 15% от ширины основного фото
        target_width = int(width * 0.30) 
        if target_width < 100: target_width = 200 # Минимальный размер, чтобы не был точкой
        
        w_percent = (target_width / float(logo.size[0]))
        target_height = int((float(logo.size[1]) * float(w_percent)))
        
        logo = logo.resize((target_width, target_height), Image.Resampling.LANCZOS)

        # Позиция: правый нижний угол с отступом 3% от края
        padding = int(width * 0.03)
        position = (width - target_width - padding, height - target_height - padding)

        # Наложение
        overlay = Image.new("RGBA", base_image.size, (0, 0, 0, 0))
        overlay.paste(logo, position, mask=logo)
        
        combined = Image.alpha_composite(base_image, overlay)
        combined.convert("RGB").save(output_image_path, "JPEG", quality=95)
        print(f"✅ Водяной знак наложен на фото {width}x{height}")

    except Exception as e:
        print(f"❌ Ошибка в watermarker: {e}")