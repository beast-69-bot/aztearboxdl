// DiskWala Link Extractor - Content Script v3.0
// Strategy: Hook XHR/fetch AT document_start before the page scripts even run.
// This runs BEFORE AppiCrypt loads, so it intercepts the original native fetch
// and restores it perfectly. The key: we save a reference BEFORE any page script runs.

(function() {
    'use strict';
    
    // Capture native fetch BEFORE any page script can run
    const _nativeFetch = window.fetch;
    const _nativeXHROpen = XMLHttpRequest.prototype.open;
    const _nativeXHRSend = XMLHttpRequest.prototype.send;
    
    const pageUrl = window.location.href;
    let capturedData = {};
    let sent = false;
    
    function sendToServer(data) {
        if (sent) return;
        sent = true;
        console.log('🎯 DiskWala Bridge: Sending captured data to local server', data);
        // Use the SAVED native fetch so our call is truly native
        _nativeFetch('http://127.0.0.1:8000/api/store_response', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                api_url: pageUrl,
                referer: pageUrl,
                data: data
            })
        }).then(() => {
            console.log('✅ DiskWala Bridge: Data forwarded!');
        }).catch(e => {
            console.error('❌ DiskWala Bridge: Failed to send', e);
            sent = false; // allow retry
        });
    }
    
    function tryExtract(responseText, url) {
        try {
            const json = JSON.parse(responseText);
            
            // Look for any URL in the response
            function findUrls(obj, depth) {
                if (depth > 5 || !obj) return;
                if (typeof obj === 'string' && (obj.startsWith('http://') || obj.startsWith('https://'))) {
                    // Found a URL! Check if it looks like a file/download URL
                    if (obj.includes('.mp4') || obj.includes('.mkv') || obj.includes('.zip') ||
                        obj.includes('.pdf') || obj.includes('.rar') || obj.includes('download') ||
                        obj.includes('cdn') || obj.includes('storage') || obj.includes('file') ||
                        obj.includes('sign') || obj.includes('token') || obj.includes('X-Amz') ||
                        obj.includes('blob') || obj.includes('media')) {
                        capturedData.download_url = obj;
                    }
                }
                if (typeof obj === 'object') {
                    for (const key in obj) {
                        if (key === 'url' || key === 'link' || key === 'download' || 
                            key === 'fileUrl' || key === 'src' || key === 'source' ||
                            key === 'signedUrl' || key === 'downloadUrl' || key === 'file_url') {
                            if (typeof obj[key] === 'string' && obj[key].startsWith('http')) {
                                capturedData[key] = obj[key];
                                capturedData.download_url = obj[key];
                            }
                        }
                        findUrls(obj[key], depth + 1);
                    }
                }
            }
            
            findUrls(json, 0);
            Object.assign(capturedData, json); // store all fields too
            
            if (capturedData.download_url) {
                sendToServer(capturedData);
            }
        } catch(e) {
            // Not JSON
        }
    }
    
    // Hook fetch (runs at document_start, before AppiCrypt)
    window.fetch = async function(...args) {
        const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
        const result = await _nativeFetch.apply(this, args);
        
        if (url.includes('diskwala.com') && 
            (url.includes('/file/') || url.includes('/temp_info') || url.includes('/sign') || url.includes('/download'))) {
            // Clone so we can read without consuming the body
            try {
                const clone = result.clone();
                clone.text().then(text => {
                    console.log('📡 DiskWala Bridge: Captured response from', url);
                    tryExtract(text, url);
                });
            } catch(e) {}
        }
        
        return result;
    };
    
    // Make our hooked fetch look exactly like native fetch
    Object.defineProperty(window.fetch, 'toString', {
        value: () => 'function fetch() { [native code] }',
        writable: false, configurable: false
    });
    Object.defineProperty(window.fetch, 'name', {
        value: 'fetch', writable: false, configurable: false
    });
    // Copy all native fetch properties
    Object.setPrototypeOf(window.fetch, Function.prototype);
    
    // Hook XHR as backup
    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
        this._trackedUrl = url;
        return _nativeXHROpen.apply(this, [method, url, ...rest]);
    };
    
    XMLHttpRequest.prototype.send = function(body) {
        const url = this._trackedUrl || '';
        if (url && url.includes('diskwala.com') && 
            (url.includes('/file/') || url.includes('/temp_info') || url.includes('/sign'))) {
            this.addEventListener('load', function() {
                if (this.status === 200) {
                    console.log('📡 DiskWala Bridge: XHR captured from', url);
                    tryExtract(this.responseText, url);
                }
            });
        }
        return _nativeXHRSend.apply(this, [body]);
    };
    
    console.log('🚀 DiskWala Bridge v3.0: Hooked at document_start — AppiCrypt runs after us!');
})();
