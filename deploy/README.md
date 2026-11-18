# Triển khai VietRP Studio trên Debian 12

Hướng dẫn này đưa VietRP Studio lên một máy Debian 12 chạy 24/7 ở nhà. Làm theo đúng thứ tự từng bước. Mọi lệnh chạy trên server, bằng một tài khoản thường có quyền `sudo`.

## 0. Sơ đồ và nguyên tắc

```
Internet → Cloudflare (TLS, tên miền) → cloudflared (tunnel, chạy trên server)
         → http://127.0.0.1:7880 (uvicorn + FastAPI, phục vụ cả frontend)
         → PostgreSQL 17 (127.0.0.1:5432)
```

- **Không mở port nào trên router.** `cloudflared` chủ động kết nối ra ngoài tới Cloudflare, nên không cần port forwarding.
- **Không dùng quick tunnel** (`trycloudflare.com`). Chỉ dùng tunnel tạo trong Zero Trust dashboard, kèm tên miền của bạn.
- **Không có Caddy hay nginx.** Cloudflare lo HTTPS.
- uvicorn chỉ lắng nghe `127.0.0.1`. Mọi request từ internet đều đi qua tunnel, nên app thấy request đến từ `127.0.0.1` và tin `CF-Connecting-IP` đúng như thiết kế.
- **Chạy đúng 1 worker.** Session và DEK nằm trong RAM của tiến trình, nên không được tăng `--workers`.

## 1. Chuẩn bị hệ thống

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y curl ca-certificates gnupg rsync git openssl
# Tuỳ chọn: đặt múi giờ để lịch backup 03:30 theo giờ Việt Nam
sudo timedatectl set-timezone Asia/Ho_Chi_Minh
```

## 2. Tạo user hệ thống và thư mục

```bash
sudo useradd --system --home-dir /opt/vietrp --no-create-home --shell /usr/sbin/nologin vietrp
sudo mkdir -p /opt/vietrp/src /opt/vietrp/backend /opt/vietrp/frontend/dist /opt/vietrp/deploy /etc/vietrp
sudo install -d -m 700 -o vietrp -g vietrp /var/backups/vietrp
```

Quy ước:
- `/opt/vietrp/src`: bản clone mã nguồn, dùng để build. Không chạy app từ đây.
- `/opt/vietrp/backend`, `/opt/vietrp/frontend/dist`, `/opt/vietrp/deploy`: bản đã triển khai. Thuộc root, service chỉ đọc.
- `/etc/vietrp/vietrp.env`: bí mật, mode 600.
- `/var/backups/vietrp`: nơi ghi dump, thuộc `vietrp`.

## 3. Cài PostgreSQL 17 (PGDG)

Debian 12 mặc định chỉ có PostgreSQL 15, nên dùng repo PGDG:

```bash
ls /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh   # file này phải tồn tại
sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y
sudo apt update
sudo apt install -y postgresql-17
```

Đảm bảo PostgreSQL chỉ nghe ở localhost:

```bash
sudo -u postgres psql -Atc "SHOW listen_addresses;"   # kết quả phải là: localhost
sudo ss -ltnp | grep 5432                              # chỉ được thấy 127.0.0.1 hoặc ::1
```

Nếu kết quả là `*` hoặc `0.0.0.0`, sửa `listen_addresses = 'localhost'` trong `/etc/postgresql/17/main/postgresql.conf`, rồi `sudo systemctl restart postgresql`.

Tạo role và database. Sinh mật khẩu trước bằng `openssl rand -hex 32`, rồi nhập khi `psql` hỏi. Dùng `\password` để mật khẩu không nằm trong lịch sử shell:

```bash
sudo -u postgres psql
```

```sql
CREATE ROLE vietrp LOGIN;
\password vietrp
CREATE DATABASE vietrp OWNER vietrp;
\q
```

Chủ database có quyền tạo extension `pgcrypto` (đây là extension "trusted"), nên migration `0001` chạy được bằng role `vietrp`, không cần superuser. Giữ mật khẩu này để điền vào `DATABASE_URL` ở bước 6.

## 4. Cài uv và Node

**uv** (quản lý Python 3.12 và virtualenv; Debian 12 chỉ có Python 3.11):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh
uv --version
```

**Node 22 LTS** (chỉ cần để build frontend; apt của Debian 12 chỉ có Node 18, quá cũ cho Vite mới):

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
node --version
```

Cách khác: build frontend trên máy dev, rồi chép thư mục `frontend/dist` lên server. Khi đó không cần cài Node trên server.

## 5. Lấy mã nguồn, build và triển khai

Clone repo vào `/opt/vietrp/src` (repo git lấy `vietrp-studio/` làm thư mục gốc). Nếu repo là private, chép thư mục `vietrp-studio/` từ máy dev vào `/opt/vietrp/src` bằng `rsync` thay cho `git clone`:

```bash
sudo git clone <URL_REPO> /opt/vietrp/src
sudo chown -R "$USER":"$USER" /opt/vietrp/src
```

Build frontend bằng tài khoản thường (không cần sudo):

```bash
cd /opt/vietrp/src/frontend
npm ci
npm run build
```

Chép code đã build vào thư mục triển khai. Lệnh này giữ nguyên `.venv` của backend (nếu bạn chép thư mục cha chứa `vietrp-studio/`, đổi `cd /opt/vietrp/src` thành `cd /opt/vietrp/src/vietrp-studio`):

```bash
cd /opt/vietrp/src
sudo rsync -a --delete --exclude '.venv' --exclude '__pycache__' backend/ /opt/vietrp/backend/
sudo rsync -a --delete frontend/dist/ /opt/vietrp/frontend/dist/
sudo rsync -a --delete deploy/ /opt/vietrp/deploy/
```

Cài dependency backend đúng theo lock file. Lệnh này tự tải Python 3.12 vào `/opt/vietrp/python`, nơi user `vietrp` đọc được:

```bash
cd /opt/vietrp/backend
sudo env UV_PYTHON_INSTALL_DIR=/opt/vietrp/python uv sync --frozen --no-dev
```

## 6. Tạo file môi trường và sinh bí mật

```bash
sudo install -m 600 -o root -g root /opt/vietrp/deploy/scripts/env.example /etc/vietrp/vietrp.env
sudoedit /etc/vietrp/vietrp.env
```

Thay các placeholder:

| Biến | Giá trị |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://vietrp:<mật khẩu từ bước 3>@127.0.0.1:5432/vietrp` |
| `VIETRP_SERVER_PEPPER` | `openssl rand -hex 32` |
| `VIETRP_SESSION_SECRET` | `openssl rand -hex 32` |
| `VIETRP_ENV` | `prod` (để sẵn trong file mẫu) |

Quy tắc:
- Mỗi dòng là `KEY=VALUE`, không có khoảng trắng quanh dấu `=`, không có dấu nháy.
- `VIETRP_SERVER_PEPPER` không được đổi sau khi đã có vault. Đổi pepper thì mọi vault hiện có sẽ không mở được.
- Kiểm tra quyền file: `sudo ls -l /etc/vietrp/vietrp.env` phải hiện `-rw------- root root`.

## 7. Cài và bật systemd

```bash
sudo cp /opt/vietrp/deploy/systemd/vietrp-api.service \
        /opt/vietrp/deploy/systemd/vietrp-backup.service \
        /opt/vietrp/deploy/systemd/vietrp-backup.timer \
        /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemd-analyze verify /etc/systemd/system/vietrp-api.service /etc/systemd/system/vietrp-backup.service
sudo systemctl enable --now vietrp-api.service
sudo systemctl enable --now vietrp-backup.timer
```

`vietrp-api.service` chạy `alembic upgrade head` trước mỗi lần khởi động, nên schema luôn khớp với code. Nếu migration lỗi, service không khởi động và log ghi rõ lỗi:

```bash
systemctl status vietrp-api --no-pager
journalctl -u vietrp-api -n 100 --no-pager
```

## 8. Cloudflare Tunnel (Zero Trust dashboard)

Tên mục trên dashboard có thể khác đôi chút tùy phiên bản. Các bước chính:

1. Đăng nhập [Cloudflare Zero Trust](https://one.dash.cloudflare.com/), vào **Networks → Tunnels → Create a tunnel**, chọn loại **Cloudflared**.
2. Đặt tên tunnel (ví dụ `vietrp-home`), rồi chọn hệ điều hành **Debian** và kiến trúc **64-bit**.
3. Dashboard hiện một lệnh có kèm token. Chạy đúng lệnh đó trên server, dạng:
   ```bash
   sudo cloudflared service install <TOKEN_TU_DASHBOARD>
   ```
   Lệnh này cài `cloudflared` thành service systemd (`cloudflared.service`). Token là bí mật: không dán vào chat, không commit, không để trong file của repo. Nếu lộ token, xoá connector trong dashboard rồi tạo lại tunnel.
4. Kiểm tra connector: `systemctl status cloudflared --no-pager`. Trên dashboard, tunnel phải chuyển sang trạng thái **Healthy**.
5. Tab **Public Hostname**, thêm:
   - Subdomain và domain: tên bạn muốn dùng (ví dụ `studio.<tên-miền-của-bạn>`);
   - Service type: `HTTP`;
   - URL: `http://127.0.0.1:7880`.
6. Mở `https://studio.<tên-miền-của-bạn>/api/health` từ điện thoại bằng 4G (không dùng Wi-Fi nhà) để thử từ ngoài.

Lưu ý:
- **Không tạo quick tunnel** và không mở port trên router.
- SSE chạy qua tunnel bình thường. App gửi `ping` mỗi 15 giây, vì Cloudflare cắt kết nối im lặng quá khoảng 100 giây.
- **Cloudflare Access** (tuỳ chọn): có thể đặt một chính sách Access trước hostname để chỉ những email được phép mới vào được trang. Lưu ý là chính sách này chặn cả người dùng khác không có trong danh sách. Passphrase vẫn bắt buộc sau đó.
- Cập nhật `cloudflared` bằng apt như mọi package khác: `sudo apt upgrade cloudflared`.

## 9. Kiểm tra

```bash
curl -fsS http://127.0.0.1:7880/api/health      # phải trả về {"status":"ok",...}
sudo ss -ltnp | grep 7880                        # phải chỉ thấy 127.0.0.1:7880
systemctl list-timers vietrp-backup.timer --no-pager
```

Sau đó mở `https://studio.<tên-miền-của-bạn>` trên trình duyệt. Thử unlock, tạo vault, và kiểm tra nút đổi theme.

## 10. Backup và khôi phục

**Lịch:** `vietrp-backup.timer` chạy mỗi ngày lúc 03:30 (cộng ngẫu nhiên tối đa 5 phút). Nếu máy tắt đúng giờ đó, lần chạy bù sẽ diễn ra khi máy bật lại (`Persistent=true`).

**Nơi lưu:** `/var/backups/vietrp/vietrp-YYYYmmdd-HHMMSS.dump` (định dạng `pg_dump -Fc`). Script giữ **14 bản gần nhất**. Có thể đổi bằng `VIETRP_BACKUP_KEEP`. Mỗi bản được kiểm tra bằng `pg_restore --list` trước khi giữ lại.

Chạy thử một lần và xem kết quả:

```bash
sudo systemctl start vietrp-backup.service
sudo ls -l /var/backups/vietrp
journalctl -u vietrp-backup -n 50 --no-pager
```

**Khôi phục:** thao tác này ghi đè dữ liệu hiện tại. Script tự chụp một bản backup an toàn trước khi khôi phục, nhưng vẫn cần xác nhận bằng biến `VIETRP_CONFIRM_RESTORE=yes`:

```bash
sudo systemctl stop vietrp-api
sudo env VIETRP_CONFIRM_RESTORE=yes bash /opt/vietrp/deploy/scripts/restore.sh /var/backups/vietrp/vietrp-YYYYmmdd-HHMMSS.dump
sudo systemctl start vietrp-api
```

**Bản backup có phải là bản sao đầy đủ không?** Dump chứa toàn bộ dữ liệu: card, world, chat, và API key đã mã hoá. Dump **không** chứa pepper và env file. Vì vậy:

- **Pepper và env file phải được sao lưu riêng**, ở nơi không nằm cùng máy với `/var/backups`: trình quản lý mật khẩu, hoặc USB để riêng. Đây là phần quan trọng nhất.
- **Mất pepper = mọi vault không còn mở được**, kể cả khi bạn còn file dump.
- Nên copy dump ra ngoài máy (ổ khác hoặc cloud). Nếu đưa lên cloud, mã hoá file trước.

## 11. Cập nhật phiên bản

```bash
# 1. Lấy mã mới và build frontend
cd /opt/vietrp/src && git pull
cd /opt/vietrp/src/frontend && npm ci && npm run build

# 2. Chép vào thư mục triển khai
cd /opt/vietrp/src
sudo rsync -a --delete --exclude '.venv' --exclude '__pycache__' backend/ /opt/vietrp/backend/
sudo rsync -a --delete frontend/dist/ /opt/vietrp/frontend/dist/
sudo rsync -a --delete deploy/ /opt/vietrp/deploy/

# 3. Cập nhật dependency, nếu lock file đổi
cd /opt/vietrp/backend && sudo env UV_PYTHON_INSTALL_DIR=/opt/vietrp/python uv sync --frozen --no-dev

# 4. Nếu unit systemd đổi, cài lại và nạp lại
sudo cp /opt/vietrp/deploy/systemd/vietrp-*.service /opt/vietrp/deploy/systemd/vietrp-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload

# 5. Khởi động lại. Migration chạy tự động trong ExecStartPre
sudo systemctl restart vietrp-api
curl -fsS http://127.0.0.1:7880/api/health
```

Khởi động lại làm mọi phiên đăng nhập mất (session nằm trong RAM), người dùng phải unlock lại. Điều này đúng theo thiết kế.

## 12. Xử lý sự cố

| Triệu chứng | Kiểm tra |
|---|---|
| `vietrp-api` không start, log có lỗi alembic | `DATABASE_URL` đúng chưa, role `vietrp` có mật khẩu đúng không, DB `vietrp` có owner `vietrp` không |
| Trang báo 502 hoặc 1033 từ Cloudflare | `systemctl status cloudflared`; Public Hostname phải trỏ `http://127.0.0.1:7880` |
| Đăng nhập xong vẫn không giữ được phiên | `VIETRP_ENV` phải là `prod` (cookie `Secure`) và truy cập qua HTTPS của Cloudflare |
| Bị báo `rate_limited` dù không đăng nhập nhiều | Kiểm tra `CF-Connecting-IP` có đi qua tunnel không; app chỉ tin header này khi request đến từ `127.0.0.1` |
| Backup báo `DATABASE_URL is not set` | Chạy bằng `sudo systemctl start vietrp-backup.service` (service tự nạp env file), không chạy script tay mà thiếu biến |

Log cần xem:

```bash
journalctl -u vietrp-api -f
journalctl -u cloudflared -n 100 --no-pager
journalctl -u vietrp-backup -n 100 --no-pager
```

Không dán nội dung env file, token của tunnel, hay `DATABASE_URL` vào chat khi hỏi về lỗi. Hãy che các giá trị bí mật trước.
