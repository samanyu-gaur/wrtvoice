# Socratic Oracle: Cloud Deployment Guide

This guide covers everything you need to do to take the refactored cloud files and successfully deploy them to **Supabase** (Database), **Render** (Backend), and **Vercel** (Frontend).

---

## 1. Setting Up Your Environment Variables (`.env`)

Create a new file named exactly `.env` (no extension) in your project root and paste the following:

```env
# 1. Supabase PostgreSQL URL
# Get this from Supabase Dashboard -> Project Settings -> Database → Connection String (URI).
# It will look like: postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT].supabase.co:5432/postgres
# IMPORTANT: Replace [YOUR-PASSWORD] with your actual database password!
SUPABASE_DB_URL=postgresql://postgres:SocraticOracleLLM@db.hupjgstbvsutfnjwptaw.supabase.co:5432/postgres

# 2. HKU Connect Llama 3.1 & Vision Endpoints
HKU_API_KEY=0602de46cc1d4617be48681af5a5f42f
```

*Note: You will use these same 2 values in the Render dashboard during backend deployment.*

---

## 2. Deploying the Database (Supabase)

1. You already created the database! The url provided inside your `.env` works perfectly.
2. *You don't need to create tables manually.* When you deploy the Render backend, the `database.py` script is programmed to automatically run `init_db()` and generate your `sessions`, `messages`, and `vision_logs` tables on startup!

---

## 3. Deploying the Backend (Render)

1. Upload/push your project to your GitHub repository (this step is complete!).
2. Go to [Render.com](https://render.com/) and click **"New" -> "Web Service"**.
3. Connect your GitHub repository.
4. **Configuration:**
   - **Name**: `socratic-oracle-backend` (or whatever you like)
   - **Branch**: `feature/vllm-backend`
   - **Environment**: Select `Docker` (Render will automatically detect the `Dockerfile` I generated).
   - **Instance Type**: Select the **Free** tier (this gives you 512MB RAM, which is completely fine now that the ML models are offloaded).
5. **Environment Variables**:
   Scroll down to the "Environment Variables" section in Render and click **Add Environment Variable** twice to add the two variables exactly as they are written:
   - Key: `SUPABASE_DB_URL` | Value: `postgresql://postgres:SocraticOracleLLM@db.hupjgstbvsutfnjwptaw.supabase.co:5432/postgres`
   - Key: `HKU_API_KEY` | Value: `0602de46cc1d4617be48681af5a5f42f`
6. Click **Create Web Service**. 
7. *Wait 3-4 minutes.* Render will download Python, install the libraries, and start your FastAPI server. Copy the URL Render gives you (e.g., `https://socratic-oracle-backend.onrender.com`).

---

## 4. Deploying the Frontend (Vercel)

Before deploying to Vercel, you need to tell your frontend how to talk to the newly deployed Render backend.

1. **Update the JavaScript URLs:**
   Open your frontend JavaScript files (inside the `static/` folder). At the very top, define the URL Render just assigned to you:
   ```javascript
   const API_BASE_URL = "https://socratic-oracle-backend.onrender.com"; // Replace with your Render URL
   ```
   *Make sure you follow the `frontend_instructions.md` file I generated previously to prefix all your `fetch()` calls with this `API_BASE_URL`.*

2. **Deploy to Vercel:**
   - Push these frontend JS changes to your GitHub repo.
   - Go to [Vercel.com](https://vercel.com/) and click **"Add New..." -> "Project"**.
   - Import your GitHub repository.
   - **Important Configuration Step**: Because your frontend files are located inside the `static/` folder (and your repo root contains python/backend files), configure Vercel's **Root Directory** setting to `static`. This tells Vercel to serve the HTML pages directly.
   - Click **Deploy**.

---

### You're Finished! 🎉
Visit the Vercel URL. Your students can now upload PDFs, talk to the AI securely, and have their chats saved permanently in the Supabase PostgreSQL database, all handled by your fast, low-memory Render backend!
