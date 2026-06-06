// ===================================================
//  Contacts & Mode
// ===================================================
const STORAGE_KEY = 'wislog_avatar_mode';

const CONTACTS = [
    { id: 'c1', name: 'ハナ',   gender: 'women', num: 12, tag: '大学の友達',    animeSeed: 'hana',  animeStyle: 'lorelei',    animeBg: 'ffd5dc,c0aede,ffdfbf' },
    { id: 'c2', name: 'ユキ',   gender: 'women', num: 25, tag: '高校からの友達', animeSeed: 'yuki',  animeStyle: 'lorelei',    animeBg: 'b6e3f4,c0aede,d1d4f9' },
    { id: 'c3', name: 'ミク',   gender: 'women', num: 47, tag: '趣味仲間',       animeSeed: 'miku',  animeStyle: 'micah',      animeBg: 'ffd5dc,d1d4f9,ffdfbf' },
    { id: 'c4', name: 'リク',   gender: 'men',   num:  8, tag: '幼馴染',         animeSeed: 'riku',  animeStyle: 'adventurer', animeBg: 'b6e3f4,c0aede,d1d4f9' },
    { id: 'c5', name: 'カイト', gender: 'men',   num: 33, tag: '職場の同僚',     animeSeed: 'kaito', animeStyle: 'adventurer', animeBg: 'c0aede,b6e3f4,ffdfbf' },
];

let currentMode        = localStorage.getItem(STORAGE_KEY) || 'real';
let currentContact     = null;
let currentTalkEndpoint = '/api/talk';

function getContactImgSrc(contact) {
    if (currentMode === '2d') {
        return `https://api.dicebear.com/9.x/${contact.animeStyle}/svg?seed=${contact.animeSeed}&backgroundColor=${contact.animeBg}&radius=50`;
    }
    return `https://randomuser.me/api/portraits/${contact.gender}/${contact.num}.jpg`;
}

function switchMode(mode) {
    currentMode = mode;
    localStorage.setItem(STORAGE_KEY, mode);
    document.getElementById('btnReal').classList.toggle('active', mode === 'real');
    document.getElementById('btn2d').classList.toggle('active',   mode === '2d');
    renderContacts();
}

function renderContacts() {
    const list = document.getElementById('contactsList');
    list.innerHTML = '';
    CONTACTS.forEach(contact => {
        const imgSrc = getContactImgSrc(contact);
        const is2D   = currentMode === '2d';
        const item   = document.createElement('div');
        item.className = 'contact-item';
        item.innerHTML = `
            <img class="contact-avatar${is2D ? ' mode-2d' : ''}" src="${imgSrc}" alt="${contact.name}"
                 onerror="this.src='https://api.dicebear.com/9.x/lorelei/svg?seed=${contact.animeSeed}&radius=50'">
            <div class="contact-info">
                <div class="contact-name">${contact.name}</div>
                <div class="contact-tag">${contact.tag}</div>
            </div>
            <button class="contact-call-btn" onclick="startCall('${contact.id}')">
                <svg viewBox="0 0 24 24" fill="white" width="20" height="20">
                    <path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/>
                </svg>
            </button>
        `;
        list.appendChild(item);
    });

    // 自己対話コンタクト（セパレーターの後に追加）
    const sep = document.createElement('div');
    sep.className = 'contact-separator';
    sep.textContent = '自己対話';
    list.appendChild(sep);

    const selfItem = document.createElement('div');
    selfItem.className = 'contact-item contact-self';
    selfItem.innerHTML = `
        <div class="self-avatar">🪞</div>
        <div class="contact-info">
            <div class="contact-name">自分</div>
            <div class="contact-tag">モデル化された自分と話す</div>
        </div>
        <button class="contact-call-btn contact-call-self" onclick="startCall('self')">
            <svg viewBox="0 0 24 24" fill="white" width="20" height="20">
                <path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/>
            </svg>
        </button>
    `;
    list.appendChild(selfItem);
}

document.getElementById('btnReal').classList.toggle('active', currentMode === 'real');
document.getElementById('btn2d').classList.toggle('active',   currentMode === '2d');
renderContacts();


// ===================================================
//  Screen Navigation
// ===================================================
function showScreen(id) {
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    document.getElementById(id).classList.add('active');
}


// ===================================================
//  Ringtone (Web Audio API)
// ===================================================
let ringtoneCtx   = null;
let ringtoneTimer = null;

function playRingtone() {
    try {
        ringtoneCtx = new (window.AudioContext || window.webkitAudioContext)();

        function tone(freq, startSec, durSec) {
            const osc  = ringtoneCtx.createOscillator();
            const gain = ringtoneCtx.createGain();
            osc.connect(gain);
            gain.connect(ringtoneCtx.destination);
            osc.type = 'sine';
            osc.frequency.value = freq;
            const t = ringtoneCtx.currentTime + startSec;
            gain.gain.setValueAtTime(0, t);
            gain.gain.linearRampToValueAtTime(0.22, t + 0.03);
            gain.gain.setValueAtTime(0.22, t + durSec - 0.05);
            gain.gain.linearRampToValueAtTime(0, t + durSec);
            osc.start(t);
            osc.stop(t + durSec);
        }

        function ring() {
            if (!ringtoneCtx) return;
            tone(480, 0,    0.4);
            tone(480, 0.55, 0.4);
        }

        ring();
        ringtoneTimer = setInterval(ring, 2200);
    } catch (e) { console.warn('Ringtone:', e); }
}

function stopRingtone() {
    if (ringtoneTimer) { clearInterval(ringtoneTimer); ringtoneTimer = null; }
    if (ringtoneCtx)   { ringtoneCtx.close().catch(() => {}); ringtoneCtx = null; }
}


// ===================================================
//  Call Flow
// ===================================================
let ringCallTimer = null;

function startCall(contactId) {
    if (contactId === 'self') {
        currentContact = { id: 'self', name: '自分', tag: '自己対話モード', animeSeed: 'self', isSelf: true };
        currentTalkEndpoint = '/api/talk_as_me';
    } else {
        currentContact = CONTACTS.find(c => c.id === contactId);
        currentTalkEndpoint = '/api/talk';
    }
    if (!currentContact) return;

    const imgSrc = getContactImgSrc(currentContact);
    const is2D   = currentMode === '2d';

    const callingAv = document.getElementById('callingAvatar');
    const callingName = document.getElementById('callingName');
    const callingTag  = document.getElementById('callingTag');
    const bg = document.getElementById('callingBg');

    if (currentContact.isSelf) {
        callingAv.src   = '';
        callingAv.style.display = 'none';
        document.getElementById('callingRingsEmoji').textContent = '🪞';
        document.getElementById('callingRingsEmoji').style.display = 'flex';
    } else {
        callingAv.style.display = '';
        document.getElementById('callingRingsEmoji').style.display = 'none';
        callingAv.src = imgSrc;
        callingAv.classList.toggle('mode-2d', is2D);
        callingAv.onerror = () => {
            callingAv.src = `https://api.dicebear.com/9.x/lorelei/svg?seed=${currentContact.animeSeed}&radius=50`;
        };
        bg.style.backgroundImage = is2D ? 'none' : `url('${imgSrc}')`;
    }

    callingName.textContent = currentContact.name;
    callingTag.textContent  = currentContact.tag;

    showScreen('screenCalling');
    playRingtone();

    ringCallTimer = setTimeout(() => {
        stopRingtone();
        connectCall();
    }, 3500);
}

function hangup() {
    clearTimeout(ringCallTimer);
    clearTimeout(moodSkipTimer);
    stopRingtone();
    autoRecordEnabled = false;
    showScreen('screenContacts');
}

function endCall() {
    autoRecordEnabled = false;
    autoRecordPaused  = false;
    if (isRecording) recognition.stop();
    speechSynthesis.cancel();
    showScreen('screenContacts');
    document.getElementById('chatArea').innerHTML = `
        <div class="chat-hint" id="chatHint">🎤 下のボタンを押して話しかけてね</div>
        <div class="typing-indicator" id="typingIndicator">
            <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        </div>
    `;
}

let moodSkipTimer = null;

function connectCall() {
    showScreen('screenMood');
    moodSkipTimer = setTimeout(skipMood, 8000);
}

function selectMood(mood) {
    clearTimeout(moodSkipTimer);
    fetch('/api/mood', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ mood }),
    }).catch(() => {});
    startCallScreen();
}

function skipMood() {
    clearTimeout(moodSkipTimer);
    startCallScreen();
}

function startCallScreen() {
    const imgSrc = getContactImgSrc(currentContact);
    const is2D   = currentMode === '2d';
    const av     = document.getElementById('inCallAvatar');
    av.src = imgSrc;
    av.classList.toggle('mode-2d', is2D);
    av.onerror = () => {
        av.src = `https://api.dicebear.com/9.x/lorelei/svg?seed=${currentContact.animeSeed}&radius=50`;
    };
    document.getElementById('inCallName').textContent = currentContact.name;
    showScreen('screenCall');
    updateStatus('通話待機中', false);
    applyTTSButton();
}


// ===================================================
//  TTS toggle
// ===================================================
const TTS_KEY    = 'wislog_tts_enabled';
const VOICE_KEY  = 'wislog_voice_value';
let ttsEnabled   = localStorage.getItem(TTS_KEY) === 'true';
let currentVoice = localStorage.getItem(VOICE_KEY) || '50021:8';

function toggleTTS() {
    ttsEnabled = !ttsEnabled;
    localStorage.setItem(TTS_KEY, ttsEnabled);
    applyTTSButton();
}

function applyTTSButton() {
    const btn = document.getElementById('ttsToggle');
    if (!btn) return;
    btn.textContent = ttsEnabled ? '🔊' : '🔇';
    btn.classList.toggle('active', ttsEnabled);
}

let _bestVoice = null;
function pickBestVoice() {
    const voices = speechSynthesis.getVoices();
    if (!voices.length) return null;
    const rules = [
        v => /Nanami.*Natural|Natural.*Nanami/i.test(v.name),
        v => /Natural/i.test(v.name) && v.lang.startsWith('ja'),
        v => v.name === 'Google 日本語',
        v => /Google/i.test(v.name) && v.lang.startsWith('ja'),
        v => v.lang === 'ja-JP',
        v => v.lang === 'ja',
    ];
    for (const rule of rules) { const f = voices.find(rule); if (f) return f; }
    return null;
}
speechSynthesis.onvoiceschanged = () => { _bestVoice = pickBestVoice(); };
_bestVoice = pickBestVoice();

let autoRecordEnabled = false;
let autoRecordPaused  = false;

function scheduleAutoRecord() {
    if (!autoRecordEnabled || autoRecordPaused) return;
    updateStatus('話しかけてね...', false);
    setTimeout(() => { if (!isRecording && !autoRecordPaused) startRecording(); }, 300);
}

function toggleRecordPause() {
    autoRecordPaused = !autoRecordPaused;
    const btn  = document.getElementById('micPauseBtn');
    if (!btn) return;
    btn.classList.toggle('paused', autoRecordPaused);
    if (autoRecordPaused) {
        if (isRecording) recognition.stop();
        updateStatus('マイク停止中', false);
    } else {
        scheduleAutoRecord();
    }
}

function requestTTS(text) {
    speakBrowser(text);
}

function speakBrowser(text) {
    if (!_bestVoice) _bestVoice = pickBestVoice();
    const u = new SpeechSynthesisUtterance(text);
    u.lang  = 'ja-JP';
    u.rate  = 1.0;
    if (_bestVoice) u.voice = _bestVoice;
    u.onend  = () => { updateStatus('通話待機中', false); scheduleAutoRecord(); };
    u.onerror = () => scheduleAutoRecord();
    speechSynthesis.speak(u);
}


// ===================================================
//  Speech Recognition
// ===================================================
const recognition = new webkitSpeechRecognition();
recognition.lang           = 'ja-JP';
recognition.interimResults = false;
recognition.continuous     = false;

let isRecording = false;

function startRecording() {
    if (isRecording) return;
    isRecording = true;
    document.getElementById('micButton').classList.add('recording');
    const label = document.getElementById('micLabel');
    label.classList.add('listening');
    label.textContent = '聞いています…';
    updateStatus('聞いています...', true);
    recognition.start();
}

recognition.onresult = async (event) => {
    const text = event.results[0][0].transcript;
    if (!text || text.trim() === '') {
        resetMic();
        updateStatus('通話待機中', false);
        return;
    }

    addBubble(text, 'user');

    await new Promise(resolve => setTimeout(resolve, 3000));

    updateStatus('考えています...', true);
    showTyping(true);

    try {
        const res       = await fetch(currentTalkEndpoint, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ text }),
        });
        const data      = await res.json();
        const replyText = data.reply;

        showTyping(false);
        addBubble(replyText, 'ai');
        autoRecordEnabled = true;

        if (ttsEnabled) {
            updateStatus('話しています...', true);
            requestTTS(replyText);
        } else {
            scheduleAutoRecord();
        }

    } catch (err) {
        console.error(err);
        showTyping(false);
        updateStatus('エラーが発生しました', false);
    }
};

recognition.onend = () => {
    isRecording = false;
    resetMic();
};

recognition.onerror = (event) => {
    console.error(event.error);
    isRecording = false;
    resetMic();
    updateStatus('マイクエラー', false);
};


// ===================================================
//  Helpers
// ===================================================
function resetMic() {
    document.getElementById('micButton').classList.remove('recording');
    const label = document.getElementById('micLabel');
    label.classList.remove('listening');
    label.textContent = 'タップして話す';
}

function addBubble(text, who) {
    const chatArea = document.getElementById('chatArea');
    const hint     = document.getElementById('chatHint');
    if (hint) hint.style.display = 'none';
    const bubble     = document.createElement('div');
    bubble.className = `bubble ${who === 'user' ? 'user-bubble' : 'ai-bubble'}`;
    bubble.textContent = text;
    chatArea.insertBefore(bubble, document.getElementById('typingIndicator'));
    chatArea.scrollTop = chatArea.scrollHeight;
}

function showTyping(show) {
    document.getElementById('typingIndicator').classList.toggle('show', show);
    if (show) document.getElementById('chatArea').scrollTop = 99999;
}

function updateStatus(msg, active) {
    const el = document.getElementById('status');
    if (el) {
        el.textContent = msg;
        el.className   = 'call-status' + (active ? ' active' : '');
    }
}
