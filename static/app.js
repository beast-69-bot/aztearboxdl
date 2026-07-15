document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("extract-form");
    const urlInput = document.getElementById("url-input");
    const submitBtn = document.getElementById("submit-btn");
    
    const loaderSection = document.getElementById("loader-section");
    const errorSection = document.getElementById("error-section");
    const resultSection = document.getElementById("result-section");
    
    const errorMessage = document.getElementById("error-message");
    const retryBtn = document.getElementById("retry-btn");
    
    const fileTitle = document.getElementById("file-title");
    const fileSize = document.getElementById("file-size");
    const fileType = document.getElementById("file-type");
    const fileThumbnailContainer = document.getElementById("file-thumbnail-container");
    const downloadBtn = document.getElementById("download-btn");
    const copyBtn = document.getElementById("copy-btn");
    
    let currentStreamUrl = "";
    
    // Form Submit Event
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const url = urlInput.value.trim();
        if (!url) return;
        
        startExtraction(url);
    });
    
    // Retry Event
    retryBtn.addEventListener("addEventListener" in retryBtn ? "click" : "onclick", () => {
        errorSection.classList.add("hidden");
        urlInput.focus();
    });
    
    // Copy Clipboard Event
    copyBtn.addEventListener("click", async () => {
        if (!currentStreamUrl) return;
        try {
            await navigator.clipboard.writeText(currentStreamUrl);
            const originalText = copyBtn.innerHTML;
            copyBtn.innerHTML = `<i class="fa-solid fa-check"></i> <span>Copied!</span>`;
            copyBtn.style.borderColor = "#10b981";
            setTimeout(() => {
                copyBtn.innerHTML = originalText;
                copyBtn.style.borderColor = "";
            }, 2000);
        } catch (err) {
            console.error("Failed to copy link: ", err);
        }
    });
    
    let pollingInterval = null;
    
    // Main extraction workflow
    async function startExtraction(url) {
        // Reset and show loader
        hideAllSections();
        loaderSection.classList.remove("hidden");
        
        // Start simulated step updates
        const stepIntervals = animateSteps();
        
        try {
            const response = await fetch("/api/extract", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url })
            });
            
            const data = await response.json();
            clearInterval(stepIntervals.intervalId);
            
            if (response.ok && data.status === "success") {
                completeAllSteps();
                setTimeout(() => { showResults(data.metadata); }, 600);
            } else if (data.status === "bridge_mode") {
                // AppiCrypt detected — use bookmarklet bridge
                startBookmarkletBridge(data.normalized_url || url);
            } else {
                startBookmarkletBridge(url);
            }
        } catch (err) {
            clearInterval(stepIntervals.intervalId);
            startBookmarkletBridge(url);
        }
    }
    
    function startBookmarkletBridge(url) {
        if (pollingInterval) clearInterval(pollingInterval);
        
        // Clean URL
        const cleanUrl = url.replace(/[\\/]+$/, '');
        
        // Bookmarklet strategy:
        // 1. Click "Copy link to open in browser" on DiskWala (it copies the download URL)
        // 2. Read clipboard
        // 3. Send URL via Image beacon (works HTTPS→HTTP, no CORS)
        // 4. Fallback: show URL in popup so user can manually copy it
        const siteOrigin = window.location.origin; // e.g. https://diskwala-extractor.onrender.com
        const bookmarkletCode = `javascript:(function(){
var ns=document.createElement('div');
ns.id='dw-bridge';
ns.style='position:fixed;top:16px;right:16px;background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;padding:16px 20px;border-radius:14px;z-index:2147483647;font-family:sans-serif;font-size:13px;box-shadow:0 8px 32px rgba(0,0,0,0.6);min-width:240px;line-height:1.5;';
ns.innerHTML='⏳ <b>DiskWala Bridge</b><br><small>Looking for download link...</small>';
document.body.appendChild(ns);
var SITE='${siteOrigin}';
function send(url){
  ns.innerHTML='✅ <b>Found!</b><br><small style="word-break:break-all">'+url.substring(0,60)+'...</small>';
  var img=new Image();
  img.src=SITE+'/api/beacon?url='+encodeURIComponent(url)+'&page='+encodeURIComponent(location.href);
  img.onerror=img.onload=function(){
    ns.innerHTML='✅ <b>Done!</b> Switch to your extractor tab<br><small>Or copy: <a href="'+url+'" style="color:#a5f3fc" target="_blank">direct link ↗</a></small>';
    setTimeout(function(){ns.remove();},10000);
  };
}
function tryClipboard(){
  navigator.clipboard.readText().then(function(txt){
    if(txt&&(txt.startsWith('http')||txt.startsWith('https'))){
      send(txt);
    } else {
      ns.innerHTML='⚠️ Clipboard: "'+txt.substring(0,30)+'"<br><small>Not a URL. Try clicking "Copy link" on DiskWala first</small>';
    }
  }).catch(function(){
    ns.innerHTML='⚠️ Clipboard denied<br><small>Allow clipboard access or copy the URL manually</small>';
  });
}
var copyBtn=null;
document.querySelectorAll('*').forEach(function(el){
  var txt=(el.innerText||el.textContent||'').toLowerCase().trim();
  if((txt.includes('copy link')||txt.includes('copy'))&&!copyBtn&&el.offsetWidth>0){
    copyBtn=el;
  }
});
if(copyBtn){
  ns.innerHTML='⏳ <b>DiskWala Bridge</b><br><small>Clicking Copy Link button...</small>';
  copyBtn.click();
  setTimeout(tryClipboard,600);
} else {
  ns.innerHTML='⚠️ Copy button not found<br><small>Click "Copy link to open in browser" manually, then click the bookmark again</small>';
  setTimeout(tryClipboard,800);
}
})();`.replace(/\n/g,'');

        
        errorSection.classList.remove("hidden");
        errorMessage.innerHTML = `
            <div class="bridge-loader-container">
                <div class="bridge-pulse">
                    <i class="fa-solid fa-satellite-dish bridge-icon"></i>
                </div>
            </div>
            <strong style="display:block; margin-bottom: 12px; color: #fff; font-size: 1.15rem;">One-Click Bridge Mode</strong>
            <span style="font-size: 0.88rem; color: #a5b4fc; line-height: 1.7; display: block; margin-bottom: 16px;">
                AppiCrypt blocks automated tools. Use this <strong style="color:#fbbf24;">2-step bridge</strong> instead:
            </span>
            <div style="background: rgba(99,102,241,0.15); border: 1px solid rgba(99,102,241,0.4); border-radius: 12px; padding: 16px; margin-bottom: 14px;">
                <div style="font-size:0.85rem; color:#c7d2fe; margin-bottom:10px; font-weight:600; letter-spacing:0.3px;">STEP 1 — Drag this button to your bookmarks bar:</div>
                <div id="bookmarklet-placeholder"></div>
                <div style="font-size:0.75rem; color:#818cf8; margin-top:8px;">👆 Drag this to your bookmarks bar (Ctrl+Shift+B to show it)</div>
            </div>
            <div style="background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.3); border-radius: 12px; padding: 16px; margin-bottom: 14px;">
                <div style="font-size:0.85rem; color:#6ee7b7; margin-bottom:8px; font-weight:600;">STEP 2 — Open DiskWala & click the bookmark:</div>
                <a href="${cleanUrl}" target="_blank" style="color: #34d399; font-weight:600; font-size:0.9rem;">🔗 Open DiskWala Page →</a>
                <div style="font-size:0.78rem; color:#6ee7b7; margin-top:6px;">Once the page loads, click <strong>⚡ DiskWala Bridge</strong> from your bookmarks bar. That's it — it auto-fetches the download URL!</div>
            </div>
            <div class="bridge-status" style="margin-top: 8px; font-size: 0.82rem; color: #818cf8; font-family: monospace;">
                <i class="fa-solid fa-circle-notch fa-spin"></i> Listening for bridge connection...
            </div>
        `;
        
        // Build the bookmarklet anchor PROGRAMMATICALLY to avoid HTML encoding issues
        const anchor = document.createElement('a');
        anchor.id = 'bookmarklet-btn';
        anchor.href = bookmarkletCode;  // set href directly — no HTML encoding issues
        anchor.textContent = '⚡ DiskWala Bridge';
        anchor.style.cssText = 'display:inline-block; background: linear-gradient(135deg,#6366f1,#8b5cf6); color:#fff; padding: 10px 20px; border-radius: 8px; text-decoration:none; font-weight:700; font-size:0.95rem; cursor:grab; border: 2px dashed rgba(255,255,255,0.3);';
        anchor.addEventListener('click', (e) => {
            e.preventDefault();
            alert('Drag this button to your Bookmarks Bar (Ctrl+Shift+B to show it), then click it on the DiskWala page!');
        });
        document.getElementById('bookmarklet-placeholder').appendChild(anchor);
        
        loaderSection.classList.add("hidden");
        
        retryBtn.innerHTML = `<span>Cancel & Back</span> <i class="fa-solid fa-chevron-left"></i>`;
        retryBtn.onclick = () => {
            if (pollingInterval) clearInterval(pollingInterval);
            errorSection.classList.add("hidden");
            urlInput.focus();
        };
        
        pollingInterval = setInterval(async () => {
            try {
                const res = await fetch(`/api/get_stored_link?url=${encodeURIComponent(cleanUrl)}`);
                const data = await res.json();
                if (data.status === "success") {
                    clearInterval(pollingInterval);
                    const statusEl = document.querySelector(".bridge-status");
                    if (statusEl) {
                        statusEl.innerHTML = `<i class="fa-solid fa-check" style="color:#10b981;"></i> Bridge connected! Download link captured!`;
                        statusEl.style.color = "#10b981";
                    }
                    setTimeout(() => {
                        hideAllSections();
                        showResults(data.metadata);
                    }, 800);
                } else if (data.status === "partial") {
                    const statusEl = document.querySelector(".bridge-status");
                    if (statusEl && !statusEl._partial) {
                        statusEl._partial = true;
                        statusEl.innerHTML = `<i class="fa-solid fa-spinner fa-spin" style="color:#f59e0b;"></i> Data incoming... waiting for download URL`;
                    }
                }
            } catch (err) {}
        }, 1500);
    }

    
    function hideAllSections() {
        loaderSection.classList.add("hidden");
        errorSection.classList.add("hidden");
        resultSection.classList.add("hidden");
        resetSteps();
    }
    
    // Animate the extraction steps sequentially to keep user engaged
    function animateSteps() {
        const steps = [
            document.getElementById("step-1"),
            document.getElementById("step-2"),
            document.getElementById("step-3"),
            document.getElementById("step-4")
        ];
        
        let currentStepIndex = 0;
        
        // Setup initial state
        steps.forEach((step, idx) => {
            if (idx === 0) {
                step.className = "step active";
                step.querySelector(".step-status").className = "fa-solid fa-circle-notch fa-spin step-status";
            } else {
                step.className = "step";
                step.querySelector(".step-status").className = "fa-regular fa-circle step-status";
            }
        });
        
        const intervalId = setInterval(() => {
            if (currentStepIndex < steps.length - 1) {
                // Complete current step
                const currentStep = steps[currentStepIndex];
                currentStep.className = "step completed";
                currentStep.querySelector(".step-status").className = "fa-solid fa-circle-check step-status";
                
                // Advance to next step
                currentStepIndex++;
                const nextStep = steps[currentStepIndex];
                nextStep.className = "step active";
                nextStep.querySelector(".step-status").className = "fa-solid fa-circle-notch fa-spin step-status";
            }
        }, 1500); // Transition every 1.5 seconds
        
        return { intervalId, steps };
    }
    
    function completeAllSteps() {
        const steps = ["step-1", "step-2", "step-3", "step-4"];
        steps.forEach(id => {
            const step = document.getElementById(id);
            if (step) {
                step.className = "step completed";
                const icon = step.querySelector(".step-status");
                if (icon) icon.className = "fa-solid fa-circle-check step-status";
            }
        });
    }
    
    function resetSteps() {
        const steps = ["step-1", "step-2", "step-3", "step-4"];
        steps.forEach(id => {
            const step = document.getElementById(id);
            if (step) {
                step.className = "step";
                const icon = step.querySelector(".step-status");
                if (icon) icon.className = "fa-regular fa-circle step-status";
            }
        });
    }
    
    // Display results in card
    function showResults(metadata) {
        loaderSection.classList.add("hidden");
        resultSection.classList.remove("hidden");
        
        // Extract fields handles alternative key formats
        const title = metadata.file_name || metadata.title || "unnamed_file";
        const bytes = metadata.file_size || metadata.size || 0;
        const mime = metadata.content_type || metadata.mime_type || "application/octet-stream";
        const downloadUrl = metadata.direct_url || metadata.download_url || "#";
        const thumbnailUrl = metadata.thumbnail_url || null;
        
        currentStreamUrl = downloadUrl;
        
        // Populate fields
        fileTitle.textContent = title;
        fileSize.textContent = formatBytes(bytes);
        fileType.textContent = mime;
        
        // Setup download button
        downloadBtn.href = downloadUrl;
        
        // Render Preview Thumbnail or Icon
        fileThumbnailContainer.innerHTML = "";
        if (thumbnailUrl && thumbnailUrl.trim() !== "") {
            const img = document.createElement("img");
            img.src = thumbnailUrl;
            img.alt = title;
            img.className = "thumbnail-image";
            img.onerror = () => {
                // Fallback to icon if image fails to load
                renderFileIcon(mime);
            };
            fileThumbnailContainer.appendChild(img);
        } else {
            renderFileIcon(mime);
        }
    }
    
    function renderFileIcon(mime) {
        const icon = document.createElement("i");
        if (mime.includes("video")) {
            icon.className = "fa-solid fa-file-video file-icon";
        } else if (mime.includes("audio") || mime.includes("music")) {
            icon.className = "fa-solid fa-file-audio file-icon";
        } else if (mime.includes("image")) {
            icon.className = "fa-solid fa-file-image file-icon";
        } else if (mime.includes("zip") || mime.includes("rar") || mime.includes("tar") || mime.includes("compressed")) {
            icon.className = "fa-solid fa-file-zipper file-icon";
        } else {
            icon.className = "fa-solid fa-file-arrow-up file-icon";
        }
        fileThumbnailContainer.appendChild(icon);
    }
    
    // Display error block
    function showError(message) {
        loaderSection.classList.add("hidden");
        errorSection.classList.remove("hidden");
        errorMessage.textContent = message;
    }
    
    // Bytes formatter utility
    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        
        // Convert to number if string
        const parsedBytes = parseFloat(bytes);
        if (isNaN(parsedBytes)) return bytes;
        
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        
        const i = Math.floor(Math.log(parsedBytes) / Math.log(k));
        
        return parseFloat((parsedBytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }
});
