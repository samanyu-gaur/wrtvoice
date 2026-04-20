# Socratic Oracle: Cloud Deployment Guide

This guide covers everything you need to successfully deploy your application. You are currently starting from **Step 1 (Render Deployment)** since your database on Supabase is already fully configured and functional.

---

## 1. Deploying the Backend (Render)

We are deploying your backend API using Render. **It is critical to use Docker** so that system dependencies like `ffmpeg` (required for voice transcriptions) are installed correctly on the server.

1. Go to [Render.com](https://render.com/) and click **"New" -> "Web Service"**.
2. Connect your GitHub repository (`wrtvoice`).
3. **Configuration:**
   - **Name**: `socratic-oracle-backend` (or whatever you prefer)
   - **Branch**: `feature/vllm-backend`
   - **Environment**: **Docker** (*Critically important! Do NOT select Python/Native!*)
   - **Build Context Directory**: *Leave blank*
   - **Dockerfile Path**: `./Dockerfile`
   - **Instance Type**: Select the **Free** tier (this gives you 512MB RAM, which works perfectly thanks to our caching optimizations).
4. **Environment Variables**:
   Scroll down to "Environment Variables", and click **Add Environment Variable** twice to add the following exactly:
   - Key: `SUPABASE_DB_URL` | Value: `postgresql://postgres:SocraticOracleLLM@db.hupjgstbvsutfnjwptaw.supabase.co:5432/postgres`
   - Key: `HKU_API_KEY` | Value: `0602de46cc1d4617be48681af5a5f42f`
5. Click **Create Web Service**.
6. Render will begin building the Docker container (it will process the Dockerfile, install `ffmpeg`, install Python libraries, and boot the Uvicorn server). Wait until the logs say `Your service is live 🎉`. 
7. At the top left of the Render dashboard, you will see your new live URL (e.g., `https://socratic-oracle-backend...onrender.com`). **Copy this URL**.

---

## 2. Deploying the Frontend (Vercel)

Before deploying to Vercel, you need to seamlessly link your frontend static files to the newly active Render backend.

1. **Update the JavaScript URLs Locally:**
   Go to your `static/js/main.js` or `static/js/api.js` (wherever you stored the fetch handlers) and define your Render URL at the top:
   ```javascript
   const API_BASE_URL = "https://your-custom-render-url.onrender.com"; // Replace with your ACTUAL Render URL
   ```
   *Make sure all `fetch()` calls in your file intelligently prefix the endpoints with this URL! E.g. `fetch(API_BASE_URL + "/api/transcribe", ...)`*

2. **Push Changes to GitHub:**
   Commit and push these frontend changes to your repository so Vercel can see them.
   ```bash
   git add static/
   git commit -m "update frontend with active render API url"
   git push origin feature/vllm-backend
   ```

3. **Deploy to Vercel:**
   - Go to [Vercel.com](https://vercel.com/) and click **"Add New..." -> "Project"**.
   - Import your GitHub repository.
   - **Important Configuration Step**: Because your frontend index.html files live inside `static/`, you MUST edit the **"Root Directory"** setting here to be `static`. 
   - Click **Deploy**.

---

### You're Finished! 🎉
Visit the final Vercel URL. Your students can now upload PDFs, use the voice-to-text transcribe functionality error-free (thanks to Docker's ffmpeg), and chat with the Socratic AI securely with their history saved directly to your Supabase PostgreSQL database!
