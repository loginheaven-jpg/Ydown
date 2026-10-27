let ws = null;
let completed = false;
let busy = false;
const resultGroups = new Map();
const audioTarget = document.getElementById('audioTarget');
const videoTarget = document.getElementById('videoTarget');
const audioFormat = document.getElementById('audioFormat');
const videoQuality = document.getElementById('videoQuality');

function updateSelection() {
    audioFormat.disabled = busy || !audioTarget.checked;
    videoQuality.disabled = busy || !videoTarget.checked;
    document.getElementById('audioSettings').classList.toggle('inactive', !audioTarget.checked);
    document.getElementById('videoSettings').classList.toggle('inactive', !videoTarget.checked);
    document.getElementById('downloadBtn').disabled = busy || !(audioTarget.checked || videoTarget.checked);
    document.getElementById('selectionHint').textContent = !(audioTarget.checked || videoTarget.checked)
        ? '오디오 또는 영상을 선택하세요.'
        : audioTarget.checked && videoTarget.checked
            ? '영상마다 오디오와 MP4를 각각 저장합니다. 최대 10개 링크 · 결과 최대 20개 파일'
            : audioTarget.checked ? '선택한 형식의 오디오 파일을 저장합니다.' : '음성이 포함된 MP4 영상을 저장합니다.';
}

try {
    const savedAudio = localStorage.getItem('ydown.audio_format');
    const savedQuality = localStorage.getItem('ydown.video_quality');
    if (['mp3', 'm4a', 'opus'].includes(savedAudio)) audioFormat.value = savedAudio;
    if (['480', '720', '1080'].includes(savedQuality)) videoQuality.value = savedQuality;
} catch (_) { /* Settings remain usable if browser storage is unavailable. */ }
for (const element of [audioTarget, videoTarget, audioFormat, videoQuality]) {
    element.addEventListener('change', () => {
        try {
            localStorage.setItem('ydown.audio_format', audioFormat.value);
            localStorage.setItem('ydown.video_quality', videoQuality.value);
        } catch (_) { /* Downloading does not depend on stored preferences. */ }
        updateSelection();
    });
}
updateSelection();

async function checkUpdate() {
    const button = document.getElementById('updateBtn');
    const status = document.getElementById('updateStatus');
    button.disabled = true;
    status.textContent = '최신 버전을 확인하고 있습니다...';
    try {
        const response = await fetch('/api/update');
        if (!response.ok) throw new Error('update failed');
        const result = await response.json();
        status.textContent = result.available
            ? `새 버전 v${result.latest_version}이 있습니다. Windows 설치 파일을 받아 실행하세요.`
            : result.message || `현재 v${result.current_version} · 최신 버전입니다.`;
    } catch (_) {
        status.textContent = '업데이트를 확인할 수 없습니다. 다운로드 / 업데이트 링크를 이용하세요.';
    } finally {
        button.disabled = false;
    }
}

function resultGroup(item, url = '') {
    if (resultGroups.has(item)) return resultGroups.get(item);
    const section = document.createElement('section');
    section.className = 'result-group';
    const heading = document.createElement('h3');
    heading.textContent = `영상 ${item}`;
    section.appendChild(heading);
    if (url) {
        const address = document.createElement('p');
        address.className = 'result-url';
        address.textContent = url;
        section.appendChild(address);
    }
    const group = {section, heading, statuses: new Map()};
    resultGroups.set(item, group);
    const container = document.getElementById('downloadLinks');
    container.appendChild(section);
    container.classList.add('has-items');
    return group;
}

function outputStatus(event, error = false) {
    const group = resultGroup(event.item);
    if (!group.statuses.has(event.kind)) {
        const status = document.createElement('p');
        status.className = 'output-status';
        group.section.appendChild(status);
        group.statuses.set(event.kind, status);
    }
    const status = group.statuses.get(event.kind);
    status.textContent = event.message.replace('[YOUTUBE_AUTH_REQUIRED]', '');
    status.style.color = error ? 'var(--error-color)' : 'var(--text-muted)';
}

function startDownload() {
    if (busy) return;
    const inputs = document.querySelectorAll('.url-input');
    const urls = Array.from(inputs).map(input => input.value.trim()).filter(Boolean);
    if (!urls.length || !(audioTarget.checked || videoTarget.checked)) {
        updateContainerStatus('error', '입력 확인');
        appendLog(!urls.length ? 'YouTube URL을 한 개 이상 입력하세요.' : '오디오 또는 영상을 선택하세요.', 'error');
        if (!urls.length) inputs[0].focus();
        return;
    }
    const request = {urls, targets: {audio: audioTarget.checked, video: videoTarget.checked},
                     audio_format: audioFormat.value, video_quality: videoQuality.value};
    busy = true;
    completed = false;
    inputs.forEach(input => input.disabled = true);
    audioTarget.disabled = videoTarget.disabled = true;
    updateSelection();
    document.getElementById('downloadBtn').classList.add('loading');
    clearLogs();
    resultGroups.clear();
    document.getElementById('downloadLinks').replaceChildren();
    document.getElementById('downloadLinks').classList.remove('has-items');
    document.getElementById('localAppFallback').hidden = true;
    updateContainerStatus('active', '처리 중...');
    try {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${location.host}/ws/download`);
    } catch (_) {
        completed = true;
        updateContainerStatus('error', '연결 오류');
        appendLog('서버에 연결할 수 없습니다.', 'error');
        resetUI();
        return;
    }
    ws.onopen = () => ws.send(JSON.stringify(request));
    ws.onmessage = message => {
        let event;
        try { event = JSON.parse(message.data); }
        catch (_) { appendLog('서버 응답을 읽을 수 없습니다.', 'error'); return; }
        if (event.type === 'item') {
            resultGroup(event.item, event.url);
            appendLog(event.message, 'active');
        } else if (event.type === 'file_ready') {
            const group = resultGroup(event.item);
            group.heading.textContent = event.title;
            const label = event.kind === 'audio' ? '오디오' : '영상';
            const link = document.createElement('a');
            link.className = 'file-link';
            link.href = event.url;
            link.download = event.filename;
            link.textContent = `✅ ${label} 다운로드 · ${event.filename}`;
            group.section.appendChild(link);
            outputStatus({...event, message: `${label} 파일 준비 완료`});
        } else if (event.type === 'progress') {
            outputStatus(event);
            appendLog(event.message, 'active');
        } else if (event.type === 'error') {
            if ((event.message || '').includes('[YOUTUBE_AUTH_REQUIRED]')) document.getElementById('localAppFallback').hidden = false;
            appendLog((event.message || '').replace('[YOUTUBE_AUTH_REQUIRED]', ''), 'error');
            if (event.item) outputStatus(event, true);
            else {
                completed = true;
                updateContainerStatus('error', '에러 발생');
            }
        } else if (event.type === 'complete') {
            completed = true;
            const state = !event.success ? 'error' : event.failed ? 'partial' : 'success';
            const label = !event.success ? '다운로드 실패' : event.failed ? '일부 완료' : '작업 완료';
            updateContainerStatus(state, `${label} · ${event.success}/${event.total}개 저장 가능`);
            appendLog(`${event.total}개 파일 중 ${event.message}`, state);
        } else if (event.message) appendLog(event.message, 'active');
    };
    ws.onerror = () => {
        updateContainerStatus('error', '연결 오류');
        appendLog('서버와의 연결이 끊어지거나 연결할 수 없습니다.', 'error');
    };
    ws.onclose = () => {
        if (!completed) {
            updateContainerStatus('error', '연결 종료');
            appendLog('완료 전에 연결이 종료되었습니다. 이미 준비된 파일은 저장할 수 있습니다.', 'error');
        }
        resetUI();
    };
}

function appendLog(message, type) {
    const box = document.getElementById('statusBox');
    if (box.textContent === 'URL을 1개 이상 입력하고 다운로드를 시작하세요.') box.textContent = '';
    const line = document.createElement('div');
    line.textContent = message;
    if (type === 'error') line.style.color = 'var(--error-color)';
    if (type === 'success') line.style.color = 'var(--success-color)';
    if (type === 'partial') line.style.color = '#f59e0b';
    box.appendChild(line);
    box.scrollTop = box.scrollHeight;
}
function clearLogs() { document.getElementById('statusBox').textContent = ''; }
function updateContainerStatus(type, text) {
    document.getElementById('statusContainer').className = 'status-container ' + type;
    const header = document.getElementById('statusHeaderTitle');
    header.textContent = text;
    header.style.color = type === 'success' ? 'var(--success-color)' : type === 'error'
        ? 'var(--error-color)' : type === 'partial' ? '#f59e0b' : 'var(--primary-color)';
}
function resetUI() {
    busy = false;
    document.querySelectorAll('.url-input').forEach(input => input.disabled = false);
    audioTarget.disabled = videoTarget.disabled = false;
    document.getElementById('downloadBtn').classList.remove('loading');
    updateSelection();
}
