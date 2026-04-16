document.addEventListener("click", function(e) {
    if (e.target && (e.target.dataset.tab === 'verify' || e.target.innerText.includes('Verify'))) {
        setTimeout(function() {
            var editor = document.getElementById('code-editor') || document.querySelector('textarea');
            var vPanel = document.getElementById('panel-verify');
            if (editor && editor.value.trim() !== "" && vPanel && !vPanel.innerText.includes('PROVEN')) {
                var vBtn = document.getElementById('btn-verify') || Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Verify'));
                if (vBtn) vBtn.click();
                else if (typeof runVerify === 'function') runVerify();
            }
        }, 150);
    }
});
console.log("NOUS Verify Fix Loaded");
