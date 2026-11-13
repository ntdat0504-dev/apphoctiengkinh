[app]

# (str) Title of your application
title = Be Hoc Tieng Kinh

# (str) Package name
package.name = apphoctiengkinh

# (str) Package domain (needed for android packaging)
package.domain = org.behoc

# (str) Source files where the let's go (relative to directory of spec)
source.dir = .

# (list) Source files to include (let's specify tflite, json, mp3 explicitly)
source.exclude_dirs = __pycache__, bin, .buildozer, .github
source.include_exts = py,png,jpg,kv,atlas,json,tflite,mp3,m4a,wav,ogg

# (str) Application versioning
version = 1.0

# (list) Application requirements
# Đã lược bỏ numpy để tránh lỗi biên dịch chéo C++ meson/ninja trên Android
requirements = python3,kivy==2.3.0,plyer,android

# (str) Supported orientations
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (list) Permissions
android.permissions = CAMERA, RECORD_AUDIO, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE

# (int) Target Android API, should be as high as possible.
android.api = 33

# (int) Minimum API your APK will support.
android.minapi = 24

# (str) Android NDK version to use
android.ndk = 25b

# (bool) Automatically accept SDK license
android.accept_sdk_license = True

# (list) Supported architectures
android.archs = arm64-v8a

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1