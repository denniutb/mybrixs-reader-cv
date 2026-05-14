const sessionReadings = [];

const imageInput = document.getElementById("imageInput");
const previewWrap = document.getElementById("previewWrap");
const previewImage = document.getElementById("previewImage");
const scanButton = document.getElementById("scanButton");
const clearButton = document.getElementById("clearButton");
const errorBox = document.getElementById("errorBox");

const fruitType = document.getElementById("fruitType");
const batchId = document.getElementById("batchId");
const thresholdInput = document.getElementById("threshold");
const farmerNote = document.getElementById("farmerNote");

const systemStatus = document.getElementById("systemStatus");
const storageStatus = document.getElementById("storageStatus");

const emptyState = document.getElementById("emptyState");
const resultBody = document.getElementById("resultBody");
const brixValue = document.getElementById("brixValue");
const confidencePill = document.getElementById("confidencePill");
const harvestDecision = document.getElementById("harvestDecision");
const scanTime = document.getElementById("scanTime");
const scanLocation = document.getElementById("scanLocation");
const readerNote = document.getElementById("readerNote");
const cloudImageWrap = document.getElementById("cloudImageWrap");
const cloudImage = document.getElementById("cloudImage");

const scanCount = document.getElementById("scanCount");
const averageBrix = document.getElementById("averageBrix");
const minBrix = document.getElementById("minBrix");
const maxBrix = document.getElementById("maxBrix");
const readyCount = document.getElementById("readyCount");
const sessionTable = document.getElementById("sessionTable");

let selectedDataUrl = null;
let selectedBase64 = null;

init();

async function init() {
  await checkHealth();
  restoreSession();
  renderSummary();
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();

    if (data.ok && data.reference_image_present) {
      systemStatus.textContent = "Reader ready";
      systemStatus.className = "status-pill";
    } else {
      systemStatus.textContent = "Reader needs attention";
      systemStatus.className = "status-pill warning";
    }

    storageStatus.textContent = data.supabase_configured
      ? "Cloud saving is active."
      : "Cloud saving is not configured; scans can still be tested.";
  } catch (error) {
    systemStatus.textContent = "System check failed";
    systemStatus.className = "status-pill error";
    storageStatus.textContent = "The app could not verify the backend health.";
  }
}

imageInput.addEventListener("change", async (event) => {
  clearError();

  const file = event.target.files?.[0];
  if (!file) {
    selectedDataUrl = null;
    selectedBase64 = null;
    scanButton.disabled = true;
    previewWrap.classList.add("hidden");
    return;
  }

  try {
    const compressed = await compressImageToJpeg(file, 1600, 0.88);
    selectedDataUrl = compressed.dataUrl;
    selectedBase64 = compressed.base64;

    previewImage.src = selectedDataUrl;
    previewWrap.classList.remove("hidden");
    scanButton.disabled = false;
  } catch (error) {
    showError(error.message || "The image could not be prepared.");
  }
});

scanButton.addEventListener("click", async () => {
  clearError();

  if (!selectedBase64) {
    showError("Choose or take a refractometer image first.");
    return;
  }

  scanButton.disabled = true;
  scanButton.textContent = "Reading…";

  try {
    const location = await getLocationSoftly();

    const payload = {
      image: selectedBase64,
      fruit_type: fruitType.value.trim() || "unspecified",
      batch_id: batchId.value.trim() || null,
      latitude: location?.latitude ?? null,
      longitude: location?.longitude ?? null,
      farmer_note: farmerNote.value.trim() || null,
    };

    const response = await fetch("/api/scan", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Scan failed.");
    }

    const threshold = parseFloat(thresholdInput.value || "12");
    const reading = {
      time: new Date().toISOString(),
      fruit: payload.fruit_type,
      batch: payload.batch_id || "—",
      brix: Number(data.brix),
      confidence: data.confidence || "medium",
      notes: data.notes || "",
      imageUrl: data.image_url || null,
      localPreview: selectedDataUrl,
      latitude: payload.latitude,
      longitude: payload.longitude,
      threshold: Number.isFinite(threshold) ? threshold : 12.0,
    };

    sessionReadings.unshift(reading);
    persistSession();
    renderLatest(reading);
    renderSummary();

  } catch (error) {
    showError(error.message || "Scan failed.");
  } finally {
    scanButton.disabled = false;
    scanButton.textContent = "Read Brix";
  }
});

clearButton.addEventListener("click", () => {
  sessionReadings.length = 0;
  localStorage.removeItem("mybrixs_session_readings");
  renderSummary();

  emptyState.classList.remove("hidden");
  resultBody.classList.add("hidden");
  cloudImageWrap.classList.add("hidden");
});

function renderLatest(reading) {
  emptyState.classList.add("hidden");
  resultBody.classList.remove("hidden");

  brixValue.textContent = reading.brix.toFixed(1);

  confidencePill.textContent = `${reading.confidence} confidence`;
  confidencePill.className = `confidence-pill ${reading.confidence}`;

  const ready = reading.brix >= reading.threshold;
  harvestDecision.textContent = ready
    ? `At/above ${reading.threshold.toFixed(1)}% threshold`
    : `Below ${reading.threshold.toFixed(1)}% threshold`;
  harvestDecision.className = ready ? "decision" : "decision not-ready";

  scanTime.textContent = new Date(reading.time).toLocaleString();

  if (reading.latitude != null && reading.longitude != null) {
    scanLocation.textContent = `📍 ${reading.latitude.toFixed(5)}, ${reading.longitude.toFixed(5)}`;
  } else {
    scanLocation.textContent = "Location unavailable";
  }

  readerNote.textContent = reading.notes || "Scan completed.";

  const imageToShow = reading.imageUrl || reading.localPreview;
  if (imageToShow) {
    cloudImage.src = imageToShow;
    cloudImageWrap.classList.remove("hidden");
  } else {
    cloudImageWrap.classList.add("hidden");
  }
}

function renderSummary() {
  scanCount.textContent = String(sessionReadings.length);

  if (!sessionReadings.length) {
    averageBrix.textContent = "—";
    minBrix.textContent = "—";
    maxBrix.textContent = "—";
    readyCount.textContent = "0";
    sessionTable.innerHTML = `<tr><td colspan="6" class="muted">No session readings yet.</td></tr>`;
    return;
  }

  const values = sessionReadings.map(item => item.brix);
  const avg = values.reduce((sum, value) => sum + value, 0) / values.length;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const ready = sessionReadings.filter(item => item.brix >= item.threshold).length;

  averageBrix.textContent = avg.toFixed(1);
  minBrix.textContent = min.toFixed(1);
  maxBrix.textContent = max.toFixed(1);
  readyCount.textContent = String(ready);

  sessionTable.innerHTML = sessionReadings
    .map(item => {
      const status = item.brix >= item.threshold ? "Ready" : "Below threshold";
      return `
        <tr>
          <td>${escapeHtml(new Date(item.time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }))}</td>
          <td>${escapeHtml(item.fruit)}</td>
          <td>${escapeHtml(item.batch)}</td>
          <td>${item.brix.toFixed(1)}%</td>
          <td>${status}</td>
          <td>${escapeHtml(item.confidence)}</td>
        </tr>
      `;
    })
    .join("");
}

function persistSession() {
  localStorage.setItem("mybrixs_session_readings", JSON.stringify(sessionReadings.slice(0, 40)));
}

function restoreSession() {
  try {
    const saved = JSON.parse(localStorage.getItem("mybrixs_session_readings") || "[]");
    if (Array.isArray(saved)) {
      sessionReadings.push(...saved);
      if (sessionReadings[0]) {
        renderLatest(sessionReadings[0]);
      }
    }
  } catch {
    localStorage.removeItem("mybrixs_session_readings");
  }
}

async function getLocationSoftly() {
  if (!navigator.geolocation) return null;

  return new Promise(resolve => {
    navigator.geolocation.getCurrentPosition(
      position => resolve({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      }),
      () => resolve(null),
      {
        enableHighAccuracy: false,
        timeout: 5000,
        maximumAge: 300000,
      }
    );
  });
}

async function compressImageToJpeg(file, maxDimension, quality) {
  const dataUrl = await readFileAsDataUrl(file);
  const img = await loadImage(dataUrl);

  const scale = Math.min(1, maxDimension / Math.max(img.width, img.height));
  const width = Math.max(1, Math.round(img.width * scale));
  const height = Math.max(1, Math.round(img.height * scale));

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;

  const ctx = canvas.getContext("2d");
  ctx.drawImage(img, 0, 0, width, height);

  const jpegDataUrl = canvas.toDataURL("image/jpeg", quality);
  const base64 = jpegDataUrl.split(",")[1];

  return {
    dataUrl: jpegDataUrl,
    base64,
  };
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("The selected image could not be read."));
    reader.readAsDataURL(file);
  });
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("The selected image could not be loaded."));
    img.src = src;
  });
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.classList.remove("hidden");
}

function clearError() {
  errorBox.textContent = "";
  errorBox.classList.add("hidden");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
