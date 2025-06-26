# 📸 TG Photo Backup

![App Logo](https://i.postimg.cc/43YZZ70R/presplash.png)

**TG Photo Backup** is a lightweight, open-source alternative to Google Photos — with a twist: it offers **unlimited photo storage** by leveraging **Telegram bots** to back up your images.

Unlike traditional cloud storage apps, this one sends your photos directly to a Telegram chat as both compressed images and original-quality files.

---

## 🚀 Features

- 🔁 **Unlimited Backup** via Telegram
- 📸 Photo upto 50 MB
- 🤖 Uses a Telegram bot and chat ID to send images
- 📁 Backup multiple folders (just separate them with commas)
- 🧠 Sync only new or previously unuploaded photos
- 💾 Backup your app's database and settings
- 🐍 Written in Python (first release, minimal UI)

---

## 📱 Getting Started

1. **Install the App** on your Android device.
2. ⚠️ Required Permissions (Important!)
  
  > 🛑 **Note for User:**  
  > This app **does not request permissions automatically**. You must grant them manually after installation.
  
  ##### Manually grant these permissions for proper functionality:
  
  1. **All Files Access**
    
  2. **Photos and Videos Access**
    
  3. **Background Activity (optional but recommended)**
    
  4. **Internet Access** (usually granted by default)
    
  
  #### ✅ How to grant manually:
  
  - Go to **Settings > Apps > TG Photo Backup > Permissions**
    
  - Enable **Files and media**, and set it to **"Allow access to all files"**
    
  - Also enable access to **Photos and Videos**
    
  
  Without these permissions, the app **cannot read your photos** or **sync them to Telegram**.
3. **Configure Your Settings:**
  - Go to the `Settings` tab.
  - Enter:
    - Your **Telegram Bot API Key**
    - Your **Chat ID**
    - **Included Storage Paths**, e.g.:
      
      ```
      /storage/emulated/0
      ```
      
    - **Excluded Storage Paths** (optional), e.g.:
      
      ```
      /storage/emulated/0/Android,/storage/emulated/0/telegram
      ```
      
4. **Save Settings & Restart App**
5. On first launch, allow some time for image thumbnail generation.
6. Choose to **Backup** manually or **Sync**:
  - Sync will upload only new or missing photos.

---

## 🧪 Notes

⚠️ This is my first release. The app might:

- Be **laggy** during image previews
- Take time to **initialize thumbnails**
- Be **slow** due to being written in Python

📌 Recommended: Use the app **only for backup/sync**, **not** for image viewing.

---

## 🤖 Telegram Bot Setup

1. Go to [@BotFather](https://t.me/BotFather)
2. Create a new bot and copy the API token.
3. Get your Telegram User ID using:  
  [@Check_Telegram_IDBot](https://t.me/Check_Telegram_IDBot)
4. Paste your API key and User ID in the app settings.

---

## 📂 Backup Data & Settings

You can back up:

- Photo metadata database
- App settings

These are stored in the **Downloads** folder on Android.

---

## 📷 Screenshots

| ![Image 1](https://i.postimg.cc/G2jDC5Nf/Screenshot-2025-06-26-23-34-37-30-39080cc9adfddaef501cc385736d2aa1-1.jpg) | ![Image 2](https://i.postimg.cc/sxDhDJCg/Screenshot-2025-06-26-23-34-42-00-39080cc9adfddaef501cc385736d2aa1-1.jpg) |
| --- | --- |
| ![Image 3](https://i.postimg.cc/m2kHvVSd/Screenshot-2025-06-26-23-34-50-43-39080cc9adfddaef501cc385736d2aa1-1.jpg) | ![Image 4](https://i.postimg.cc/Gt7sBsbJ/Screenshot-2025-06-26-23-35-01-99-39080cc9adfddaef501cc385736d2aa1-1.jpg) |
| ![Image 5](https://i.postimg.cc/YqPWMgnt/Screenshot-2025-06-26-23-35-19-45-39080cc9adfddaef501cc385736d2aa1.jpg) | ![Image 6](https://i.postimg.cc/9QqqMMKZ/Screenshot-2025-06-26-23-35-47-61-39080cc9adfddaef501cc385736d2aa1.jpg) |
| ![Image 7](https://i.postimg.cc/Zqtvymzg/Screenshot-2025-06-26-23-36-03-06-39080cc9adfddaef501cc385736d2aa1.jpg) |     |

---

## 💬 Feedback

Found a bug or have a feature request?
Reach out to me on Telegram: [@Randomrumon](https://t.me/Randomrumon)

---

## 📜 License

This project is open-source and licensed under the [MIT License](LICENSE).
