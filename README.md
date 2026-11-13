# App Học tiếng Kinh (Offline)

Ứng dụng học tiếng Kinh (tiếng Việt) offline dành cho trẻ em dân tộc thiểu số, viết bằng Python + Kivy.

**Bước 5 (hiện tại):** máy trạng thái nhận diện minh họa + 2 màn hình (chính / thư viện) + lưu từ offline. Camera (bước 3) và âm thanh (bước 4) giữ nguyên hoạt động. NHẬN DIỆN vẫn là **MINH HỌA — chưa có AI**.

## Cấu trúc

```
main.py                       # giao diện + máy trạng thái + ScreenManager 2 màn hình
vocabulary_store.py           # logic lưu/đọc danh sách từ đã lưu (tách khỏi UI)
data/sample_vocabulary.json   # dữ liệu từ vựng mẫu (trường chưa xác minh để null)
data/saved_vocabulary.json    # danh sách ID từ do bé lưu (app tự ghi/đọc)
assets/images/                # hình minh họa: <id>.png (thiếu → giữ chỗ kèm tên đồ vật)
assets/audio/                 # âm thanh: vi_<id>.mp3 / dt_<id>.mp3
```

## Máy trạng thái nhận diện (bước 5)

Một biến trạng thái duy nhất: `IDLE → CAMERA_ON → CAPTURED → RESULT`.

- **BẬT CAMERA**: IDLE → CAMERA_ON (camera thật; nếu lỗi → chế độ MÔ PHỎNG, có nhãn MÔ PHỎNG trên khung). Nút đổi thành **TẮT CAMERA** (về IDLE).
- **CHỤP ẢNH**: CAMERA_ON → CAPTURED (camera thật: đóng băng khung hình; mô phỏng: khung "ẢNH MÔ PHỎNG — CHƯA CHỤP BẰNG CAMERA THẬT").
- **NHẬN DIỆN**: CAPTURED → RESULT, chọn ngẫu nhiên 1 đồ vật từ dữ liệu mẫu. Mọi kết quả mang nhãn **"KẾT QUẢ MINH HỌA — CHƯA CÓ AI NHẬN DIỆN"**.
- **CHỤP LẠI**: CAPTURED/RESULT → CAMERA_ON (xóa kết quả).
- **QUÉT LẠI**: bất kỳ trạng thái → IDLE (xóa kết quả cũ, tắt camera, giải phóng âm thanh).
- Thao tác không hợp lệ theo trạng thái bị bỏ qua; các nút tự bật/tắt (disabled) theo trạng thái.

## Thư viện từ vựng (màn hình `library`)

- Nút **THƯ VIỆN** mở màn hình **"TỪ VỰNG CỦA BÉ"** với 2 khu riêng biệt: **ĐÃ LƯU CỦA BÉ** và **ĐỒ VẬT MẪU ĐỂ HỌC** — đồ vật mẫu KHÔNG bị coi là từ đã học.
- Thẻ bo góc gồm: hình minh họa (hoặc giữ chỗ kèm tên), tên tiếng Kinh, từ dân tộc nếu đã xác minh, trạng thái ĐÃ LƯU/CHƯA LƯU.
- Bấm thẻ → hộp thoại chi tiết: hình, tên, bản dịch (Chưa có bản dịch nếu null), nút LƯU TỪ/BỎ LƯU, nút ĐÓNG.
- ScrollView + GridLayout 2 cột, thẻ co giãn theo cửa sổ; thông báo thân thiện khi chưa lưu từ nào.

## Lưu từ vựng offline (`data/saved_vocabulary.json`)

- Chỉ lưu ID: `{"saved_ids": ["qua_chuoi", ...]}` — khi hiển thị lấy thông tin từ dữ liệu mẫu, không lưu trùng nội dung.
- Không lưu trùng ID; ghi tệp tự tạo thư mục đích; không bao giờ ghi đè `sample_vocabulary.json`.
- Tệp chưa tồn tại → danh sách rỗng; tệp lỗi JSON → thông báo dễ hiểu + danh sách mới, app không sập.

## Schema dữ liệu (`data/sample_vocabulary.json`)

Mỗi mục trong `tu_vung` gồm 7 trường: `id`, `vietnamese`, `ethnic_language`,
`ethnic_word`, `audio_vietnamese`, `audio_ethnic`, `translation_verified`.

**Nguyên tắc:** không bịa từ dân tộc hay đường dẫn âm thanh. Trường chưa xác minh để
`null` → giao diện hiển thị "Chưa có bản dịch" / "Chưa có âm thanh". Tệp thiếu, JSON
lỗi hoặc rỗng → ứng dụng thông báo trên dòng trạng thái và dùng dữ liệu dự phòng,
không sập.

## Cài đặt & chạy

```bash
pip install kivy
pip install "opencv-python<5"   # chỉ làm driver webcam trên Windows (xem phần Camera)
python main.py
```

Trên Windows cửa sổ xem trước mở ở kích thước 360x640 (tỉ lệ 9:16).

## Camera

- Ứng dụng dùng `kivy.uix.camera.Camera` gốc của Kivy — **KHÔNG có `import cv2` trong mã nguồn**, không dùng OpenCV để xử lý ảnh.
- Windows (máy phát triển): Kivy 2.3 đã loại bỏ provider GStreamer, provider khả dụng duy nhất là OpenCV — cần `pip install "opencv-python<5"` (bản 5.x chưa được provider của Kivy hỗ trợ, sẽ lỗi `has no attribute 'fps'`). Gói này chỉ đóng vai trò driver webcam, gỡ bỏ bất cứ lúc nào mà không ảnh hưởng mã nguồn.
- Nút "Bật Camera" là nút chức năng kép: lần 1 bật và đổi nhãn thành "Tắt Camera", lần 2 tắt và trả lại nhãn cũ.
- Camera phần cứng được giải phóng ngay khi: bấm "Tắt Camera", đóng ứng dụng (`on_stop`), hoặc ứng dụng bị ẩn về nền (`on_pause` trên Android).
- Lỗi (không tìm thấy camera, thiếu driver, chưa cấp quyền) hiển thị thân thiện ngay trên khung đen của camera, ứng dụng không bị sập.

## Đóng gói Android (bước 6)

- `buildozer.spec` đã cấu hình sẵn: tên `BÉ HỌC TIẾNG KINH`, package `org.duan.tiengkinh.behoctiengkinh`,
  `requirements = python3,kivy==2.3.1,pillow` (KHÔNG opencv — Android dùng provider camera mặc định),
  `orientation = portrait`, quyền duy nhất `CAMERA`, `source.include_exts` đủ py/kv/json/png/jpg/ttf/mp3/wav/ogg.
- Buildozer **không chạy trực tiếp trên Windows** — dùng WSL/Ubuntu/Linux/macOS.
- Trên Android, tệp từ đã lưu ghi vào `user_data_dir` (vùng sandbox riêng của app);
  dữ liệu mẫu và tài nguyên đọc từ bản đóng gói, chỉ đọc.
- Quyền CAMERA là "dangerous permission": p4a tự mở hộp thoại xin quyền lần đầu chạy. Xem log qua `adb logcat`.

CHƯA KIỂM THỬ TRÊN ANDROID.

## Âm thanh

- Nút "Phát âm thanh" phát tệp local bằng `kivy.core.audio.SoundLoader` — **không dùng pyttsx3, TTS online hay API mạng**, không tự sinh âm đọc giả.
- Thứ tự tìm tệp cho từ có `id` = X theo chiều học hiện tại:
  - Chiều **Tiếng Kinh → Tiếng dân tộc**: trường `audio_vietnamese` trong JSON (nếu có), sau đó `assets/audio/vi_X.mp3`, `vi_X.wav`, `vi_X.ogg`.
  - Chiều **Tiếng dân tộc → Tiếng Kinh**: trường `audio_ethnic`, sau đó `assets/audio/dt_X.mp3`, `dt_X.wav`, `dt_X.ogg`.
- JSON vẫn giữ `null` cho các trường âm thanh khi chưa có tệp thật — ứng dụng chỉ phát tệp tồn tại thực trên đĩa.
- Thiếu tệp hoặc định dạng không đọc được → dòng trạng thái hiển thị **"Chưa có âm thanh"**, ứng dụng không sập.
- Âm đang phát được dừng + giải phóng khi: đổi từ vựng (Quét lại), đổi chiều học, bấm phát từ mới, đóng ứng dụng, ẩn ứng dụng về nền.
- Windows: MP3/WAV/OGG phát qua SDL2_mixer (có sẵn trong `kivy_deps.sdl2`).
- **Android: khả năng hỗ trợ định dạng âm thanh cần được xác minh riêng** khi đóng gói (ưu tiên `.ogg`/`.wav` nếu MP3 lỗi). CHƯA KIỂM THỬ TRÊN ANDROID.

### Hướng dẫn đặt tệp âm thanh để kiểm thử trên Windows

1. Chuẩn bị tệp MP3 hợp lệ (giọng người thật, không phải âm sinh) với tên đúng quy ước:
   `vi_qua_chuoi.mp3`, `vi_cai_coc.mp3`, `vi_quyen_sach.mp3`, `vi_con_meo.mp3`, `vi_chiec_but.mp3`.
2. Sao chép vào `assets/audio/`.
3. Chạy `python main.py` → bấm "Quét lại" để chọn từ → bấm "Phát âm thanh" → nghe thử và xem dòng trạng thái.
4. Muốn có âm cho chiều dân tộc → Kinh: đặt thêm tệp `dt_<id>.mp3` tương ứng.

## Ghi chú

- Nếu chữ tiếng Việt hiển thị thiếu dấu, đặt một tệp font `.ttf` (ví dụ DejaVuSans, Roboto đầy đủ) vào `assets/fonts/` — ứng dụng sẽ tự dùng font đó.
