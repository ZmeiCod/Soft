import os
import html
import mimetypes
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import unquote, quote

# Папки для обмена
UPLOAD_DIR = "MyFiles"     # Сюда сохраняются файлы с телефона
DOWNLOAD_DIR = "ToPhone"   # Отсюда файлы скачиваются на телефон

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
PORT = 8080

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            
            # Получаем список файлов для скачивания
            files = []
            if os.path.exists(DOWNLOAD_DIR):
                files = [f for f in os.listdir(DOWNLOAD_DIR) if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))]
                files.sort()
            
            # Формируем HTML-список ссылок
            file_links = ""
            if files:
                for f in files:
                    safe_f = quote(f) # Кодируем имя файла для URL
                    file_links += f'<li><a href="/download/{safe_f}" download>📄 {html.escape(f)}</a></li>\n'
            else:
                file_links = "<li><i>Папка пуста. Положите файлы в папку 'ToPhone' рядом с сервером.</i></li>"

            # Полноценная мобильная страница
            page = f"""
            <!DOCTYPE html>
            <html lang="ru">
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Обмен файлами</title>
                <style>
                    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 20px; background: #f4f6f8; color: #333; }}
                    .card {{ background: #fff; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 20px; }}
                    h2 {{ margin-top: 0; font-size: 20px; }}
                    input[type="file"] {{ margin-bottom: 15px; width: 100%; }}
                    button {{ background: #007bff; color: white; border: none; padding: 12px 24px; border-radius: 8px; font-size: 16px; cursor: pointer; width: 100%; }}
                    button:hover {{ background: #0056b3; }}
                    ul {{ padding-left: 0; list-style-type: none; }}
                    li {{ margin-bottom: 12px; background: #f8f9fa; padding: 12px; border-radius: 8px; }}
                    a {{ color: #007bff; text-decoration: none; word-break: break-all; font-weight: 500; }}
                    a:hover {{ text-decoration: underline; }}
                    .hint {{ font-size: 14px; color: #6c757d; margin-top: 15px; text-align: center; }}
                </style>
            </head>
            <body>
                <div class="card">
                    <h2>📷 Загрузка на ПК</h2>
                    <form action="/upload" method="post" enctype="multipart/form-data">
                        <input type="file" name="file" multiple>
                        <button type="submit">Отправить на ПК</button>
                    </form>
                </div>
                
                <div class="card">
                    <h2>📥 Скачать с ПК</h2>
                    <ul>
                        {file_links}
                    </ul>
                    <p class="hint">Файлы берутся из папки <b>ToPhone</b></p>
                </div>
            </body>
            </html>
            """
            self.wfile.write(page.encode("utf-8"))
            
        # Обработчик скачивания файлов
        elif self.path.startswith("/download/"):
            filename = unquote(self.path[len("/download/"):])
            filename = os.path.basename(filename) # Защита от перехода по папкам выше (../)
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            
            if os.path.exists(filepath) and os.path.isfile(filepath):
                # Определяем MIME-тип файла
                mime_type, _ = mimetypes.guess_type(filepath)
                if not mime_type:
                    mime_type = "application/octet-stream"
                    
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                # Указываем браузеру, что файл нужно скачать, а не открыть
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(os.path.getsize(filepath)))
                self.end_headers()
                
                with open(filepath, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "File not found")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/upload":
            self.send_error(404)
            return

        ctype = self.headers.get("Content-Type", "")
        boundary = None
        for part in ctype.split(";"):
            part = part.strip() 
            if part.startswith("boundary="):
                boundary = part[len("boundary="):].strip('"')
                break

        if not boundary:
            self.send_error(400, "No boundary")
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        boundary_bytes = ("--" + boundary).encode()
        parts = body.split(boundary_bytes)

        saved = []
        for part in parts:
            if b"Content-Disposition" not in part:
                continue
            
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue
                
            header_block = part[:header_end].decode("utf-8", errors="ignore")
            content = part[header_end + 4:]
            
            if content.endswith(b"\r\n"):
                content = content[:-2]

            filename = None
            for line in header_block.split("\r\n"):
                if "filename=" in line:
                    idx = line.find('filename="')
                    if idx != -1:
                        rest = line[idx + 10:]
                        end = rest.find('"')
                        if end != -1:
                            filename = rest[:end]
            
            if not filename:
                continue
                
            filename = unquote(filename)
            filename = os.path.basename(filename)

            base, ext = os.path.splitext(filename)
            target = os.path.join(UPLOAD_DIR, filename)
            i = 1
            while os.path.exists(target):
                target = os.path.join(UPLOAD_DIR, f"{base}_{i}{ext}")
                i += 1

            with open(target, "wb") as f:
                f.write(content)
            saved.append(filename)

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        msg = f"✅ Сохранено {len(saved)} файл(ов): \n" + "\n".join(saved)
        self.wfile.write(msg.encode("utf-8")) 
        print(f"[OK] {msg}")

    def log_message(self, format, *args):
        print(f"[{self.client_address[0]}] {args[0]}")

if __name__ == "__main__":
    # Автоматически определяем локальный IP-адрес ПК в сети
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = "127.0.0.1"
    finally:
        s.close()
    
    print(f"🚀 Сервер запущен на порту {PORT}")
    print(f"📂 Загрузка НА ПК -> папка: {os.path.abspath(UPLOAD_DIR)}")
    print(f"📂 Скачивание С ПК -> папка: {os.path.abspath(DOWNLOAD_DIR)}")
    print(f"📱 Откройте на планшете/телефоне: http://{local_ip}:{PORT}")
    print("Нажмите Ctrl+C для остановки\n")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()