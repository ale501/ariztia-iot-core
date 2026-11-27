/* =====================================================================
   WIDGET FLOTANTE DE CHATBOT IA — ARIZTÍA IoT
   ===================================================================== */

(function () {
  // 1. Inyectar estilos CSS del Chatbot
  const estilo = document.createElement('style');
  estilo.textContent = `
    .chat-bubble-btn {
      position: fixed;
      bottom: 24px;
      right: 24px;
      width: 58px;
      height: 58px;
      border-radius: 50%;
      background: linear-gradient(135deg, #2563eb 0%, #06b6d4 100%);
      box-shadow: 0 8px 25px rgba(37, 99, 235, 0.45);
      border: 2px solid rgba(255, 255, 255, 0.2);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.7rem;
      z-index: 99999;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .chat-bubble-btn:hover {
      transform: scale(1.08) translateY(-2px);
      box-shadow: 0 12px 30px rgba(6, 182, 212, 0.6);
    }
    .chat-bubble-badge {
      position: absolute;
      top: -2px;
      right: -2px;
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: #10b981;
      border: 2px solid #090c10;
    }
    .chat-window {
      position: fixed;
      bottom: 95px;
      right: 24px;
      width: 380px;
      max-width: calc(100vw - 40px);
      height: 530px;
      max-height: calc(100vh - 120px);
      background: rgba(15, 20, 28, 0.95);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 18px;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.8), 0 0 30px rgba(37, 99, 235, 0.2);
      display: none;
      flex-direction: column;
      overflow: hidden;
      z-index: 99999;
      font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
      animation: chat-appear 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .chat-window.visible {
      display: flex;
    }
    @keyframes chat-appear {
      from { opacity: 0; transform: translateY(15px) scale(0.96); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }
    .chat-header {
      padding: 1rem 1.2rem;
      background: rgba(22, 28, 42, 0.8);
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .chat-header-title {
      display: flex;
      align-items: center;
      gap: 0.6rem;
    }
    .chat-avatar {
      width: 34px;
      height: 34px;
      border-radius: 10px;
      background: linear-gradient(135deg, #2563eb 0%, #06b6d4 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.1rem;
    }
    .chat-close-btn {
      background: transparent;
      border: none;
      color: #94a3b8;
      font-size: 1.2rem;
      cursor: pointer;
      padding: 0.2rem 0.5rem;
      border-radius: 6px;
      width: auto;
      margin: 0;
      box-shadow: none;
    }
    .chat-close-btn:hover {
      background: rgba(255, 255, 255, 0.1);
      color: #fff;
    }
    .chat-messages {
      flex: 1;
      padding: 1rem;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 0.8rem;
    }
    .chat-msg {
      max-width: 85%;
      padding: 0.65rem 0.9rem;
      border-radius: 12px;
      font-size: 0.85rem;
      line-height: 1.45;
      word-break: break-word;
    }
    .chat-msg-bot {
      align-self: flex-start;
      background: rgba(30, 41, 59, 0.7);
      border: 1px solid rgba(255, 255, 255, 0.08);
      color: #f1f5f9;
      border-bottom-left-radius: 3px;
    }
    .chat-msg-user {
      align-self: flex-end;
      background: linear-gradient(135deg, #2563eb 0%, #3b82f6 100%);
      color: #ffffff;
      border-bottom-right-radius: 3px;
    }
    .chat-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
      margin-top: 0.5rem;
    }
    .chat-chip {
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 999px;
      padding: 0.25rem 0.65rem;
      font-size: 0.74rem;
      color: #38bdf8;
      cursor: pointer;
      transition: all 0.2s ease;
      display: inline-block;
    }
    .chat-chip:hover {
      background: rgba(6, 182, 212, 0.2);
      border-color: rgba(6, 182, 212, 0.4);
      color: #fff;
    }
    .chat-input-area {
      padding: 0.8rem 1rem;
      background: rgba(18, 23, 34, 0.95);
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      display: flex;
      gap: 0.5rem;
    }
    .chat-input {
      flex: 1;
      padding: 0.65rem 0.85rem;
      background: rgba(10, 14, 22, 0.7);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 8px;
      color: #fff;
      font-size: 0.85rem;
      outline: none;
      font-family: inherit;
    }
    .chat-input:focus {
      border-color: #3b82f6;
    }
    .chat-send-btn {
      width: auto;
      padding: 0.65rem 0.95rem;
      margin: 0;
      font-size: 0.9rem;
      border-radius: 8px;
    }
  `;
  document.head.appendChild(estilo);

  // 2. Inyectar HTML del Widget
  const contenedor = document.createElement('div');
  contenedor.innerHTML = `
    <div class="chat-bubble-btn" id="chatBubble" title="Asistente Virtual Ariztía">
      <span>🤖</span>
      <div class="chat-bubble-badge"></div>
    </div>

    <div class="chat-window" id="chatWindow">
      <div class="chat-header">
        <div class="chat-header-title">
          <div class="chat-avatar">🤖</div>
          <div>
            <div style="font-size: 0.9rem; font-weight: 700; color: #fff;">Asistente Ariztía AI</div>
            <div style="font-size: 0.72rem; color: #34d399; display: flex; align-items: center; gap: 0.3rem;">
              <span style="width: 6px; height: 6px; border-radius: 50%; background: #10b981;"></span> Telemetría en vivo
            </div>
          </div>
        </div>
        <button class="chat-close-btn" id="chatClose">&times;</button>
      </div>

      <div class="chat-messages" id="chatMessages">
        <div class="chat-msg chat-msg-bot">
          👋 ¡Hola! Soy el asistente inteligente de <strong>Ariztía IoT</strong>. Monitoreo tus galpones en tiempo real y puedo enviar reportes a tu <strong>WhatsApp</strong> o <strong>Telegram</strong>.
          <div class="chat-chips">
            <span class="chat-chip" onclick="enviarMensajeChat('¿Cuál es la temperatura y el IEC?')">🌡️ Temperatura e IEC</span>
            <span class="chat-chip" onclick="enviarMensajeChat('¿Cómo están los pollitos?')">🐣 Tracking Pollos</span>
            <span class="chat-chip" onclick="enviarMensajeChat('¿Hay alguna alerta activa?')">🚨 Alertas</span>
            <span class="chat-chip" onclick="enviarMensajeChat('Enviar reporte a mi WhatsApp')">📲 Test WhatsApp</span>
          </div>
        </div>
      </div>

      <form class="chat-input-area" id="chatForm">
        <input type="text" class="chat-input" id="chatInput" placeholder="Pregunta sobre el galpón o WhatsApp..." autocomplete="off">
        <button type="submit" class="chat-send-btn">&rarr;</button>
      </form>
    </div>
  `;
  document.body.appendChild(contenedor);

  // 3. Lógica del Chatbot
  const bubble = document.getElementById('chatBubble');
  const windowEl = document.getElementById('chatWindow');
  const closeBtn = document.getElementById('chatClose');
  const form = document.getElementById('chatForm');
  const input = document.getElementById('chatInput');
  const messages = document.getElementById('chatMessages');

  bubble.addEventListener('click', () => {
    windowEl.classList.toggle('visible');
    if (windowEl.classList.contains('visible')) {
      input.focus();
    }
  });

  closeBtn.addEventListener('click', () => {
    windowEl.classList.remove('visible');
  });

  function formatearTexto(txt) {
    if (!txt) return '';
    return txt
      .replace(/\n/g, '<br>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/`(.*?)`/g, '<code style="background: rgba(0,0,0,0.3); padding: 0.1rem 0.3rem; border-radius: 4px; font-family: monospace;">$1</code>');
  }

  function agregarMensaje(remitente, texto, sugerencias = []) {
    const msg = document.createElement('div');
    msg.className = `chat-msg chat-msg-${remitente}`;
    msg.innerHTML = formatearTexto(texto);

    if (sugerencias && sugerencias.length > 0) {
      const chipsContainer = document.createElement('div');
      chipsContainer.className = 'chat-chips';
      sugerencias.forEach(s => {
        const chip = document.createElement('span');
        chip.className = 'chat-chip';
        chip.textContent = s;
        chip.onclick = () => enviarMensajeChat(s);
        chipsContainer.appendChild(chip);
      });
      msg.appendChild(chipsContainer);
    }

    messages.appendChild(msg);
    messages.scrollTop = messages.scrollHeight;
  }

  window.enviarMensajeChat = async function (texto) {
    if (!texto || !texto.trim()) return;

    agregarMensaje('user', texto);
    input.value = '';

    // Mensaje temporal "pensando..."
    const loading = document.createElement('div');
    loading.className = 'chat-msg chat-msg-bot';
    loading.id = 'chatLoading';
    loading.innerHTML = '<span style="opacity: 0.7;">Analizando telemetría del galpón...</span>';
    messages.appendChild(loading);
    messages.scrollTop = messages.scrollHeight;

    try {
      const res = await fetch('/api/chatbot', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mensaje: texto })
      });
      const data = await res.json();
      
      const loadEl = document.getElementById('chatLoading');
      if (loadEl) loadEl.remove();

      if (data.ok && data.resultado) {
        agregarMensaje('bot', data.resultado.respuesta, data.resultado.sugerencias);
      } else {
        agregarMensaje('bot', '⚠️ No pude obtener respuesta del backend ambiental.');
      }
    } catch (err) {
      const loadEl = document.getElementById('chatLoading');
      if (loadEl) loadEl.remove();
      agregarMensaje('bot', '⚠️ Error conectando al backend de Ariztía (puerto 5001). Asegúrate de que `app_ariztia.py` esté iniciado.');
    }
  };

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    enviarMensajeChat(input.value);
  });
})();
