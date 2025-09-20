// ===== Configurações e Constantes =====
const CONFIG = {
  BASE_URL: localStorage.getItem("apiUrl") || "http://127.0.0.1:8000/api/v1",
  MAX_FILE_SIZE: 10 * 1024 * 1024, // 10MB
  SUPPORTED_FORMATS: ["image/jpeg", "image/png", "image/webp", "image/bmp", "image/gif"],
  DEBOUNCE_DELAY: 300,
};

// ===== Estado global =====
const STATE = {
  products: [],
  lastImageFile: null,
  lastAIResult: null,
  lastImageHash: null,
  currentPage: "identify",
  isLoading: false,
  connectionStatus: "checking",
};

// ===== Cache de Elementos DOM =====
const DOM = {};

// ===== Utilitários =====
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// Sistema de logging
const Logger = {
  log: (message, type = "info") => {
    const timestamp = new Date().toLocaleTimeString();
    const logEntry = `[${timestamp}] ${type.toUpperCase()}: ${message}`;
    console.log(logEntry);

    if (DOM.logsContent) {
      DOM.logsContent.textContent += "\n" + logEntry;
      DOM.logsContent.scrollTop = DOM.logsContent.scrollHeight;
    }

    if (type === "error" || type === "success") {
      showNotification(message, type);
    }
  },
  clear: () => {
    if (DOM.logsContent) DOM.logsContent.textContent = "";
  }
};

/**
 * Exibe um modal de confirmação profissional em vez do confirm() padrão.
 * @param {string} title - O título do modal.
 * @param {string} message - A mensagem de confirmação.
 * @returns {Promise<boolean>} - Resolve como true se o usuário confirmar, false caso contrário.
 */
function showConfirmModal({ title, message, okText = "Confirmar", okClass = "btn-danger" }) {
  const overlay = $('#confirmOverlay');
  if (!overlay) return Promise.resolve(false);

  $('#confirmTitle').textContent = title;
  $('#confirmMessage').innerHTML = message;
  const okBtn = $('#confirmOk');
  okBtn.textContent = okText;
  okBtn.className = `btn ${okClass}`;

  overlay.style.display = 'flex';
  setTimeout(() => overlay.classList.add('visible'), 10);

  return new Promise(resolve => {
    const handleOk = () => { closeModal(); resolve(true); };
    const handleCancel = () => { closeModal(); resolve(false); };
    const handleOverlayClick = (e) => { if (e.target === overlay) handleCancel(); };

    const closeModal = () => {
      overlay.classList.remove('visible');
      setTimeout(() => {
        overlay.style.display = 'none';
        okBtn.removeEventListener('click', handleOk);
        $('#confirmCancel').removeEventListener('click', handleCancel);
        overlay.removeEventListener('click', handleOverlayClick);
      }, 300);
    };

    okBtn.addEventListener('click', handleOk, { once: true });
    $('#confirmCancel').addEventListener('click', handleCancel, { once: true });
    overlay.addEventListener('click', handleOverlayClick);
  });
}


// Sistema de notificações
function showNotification(message, type = "info", duration = 5000) {
  const container = DOM.notificationContainer;
  if (!container) return;

  const notification = document.createElement("div");
  notification.className = `notification notification-${type}`;
  notification.innerHTML = `
    <i class="fas fa-${getNotificationIcon(type)}"></i>
    <span>${message}</span>
    <button>&times;</button>
  `;

  notification.querySelector('button').addEventListener('click', () => notification.remove());
  container.appendChild(notification);

  if (duration > 0) {
    setTimeout(() => notification.remove(), duration);
  }
}

function getNotificationIcon(type) {
  const icons = {
    success: "check-circle", error: "exclamation-circle", info: "info-circle"
  };
  return icons[type] || "info-circle";
}


function getNotificationBgColor(type) {
  const colors = {
    success: "#38a169",
    error: "#e53e3e",
    warning: "#dd6b20",
    info: "#3182ce",
    loading: "#6b7280"
  };
  return colors[type] || "#3182ce";
}

// Debounce para performance
function debounce(func, wait) {
  let timeout;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}
/**
 * Gerencia o estado de carregamento de um botão, mostrando um spinner.
 * @param {HTMLElement} button O elemento do botão a ser modificado.
 * @param {boolean} isLoading True para ativar o estado de carregamento, false para desativar.
 * @param {string} [loadingText='Identificando...'] O texto para exibir ao lado do spinner.
 */
// Gerencia estado de loading de botões
function setButtonLoadingState(button, isLoading, loadingText = 'Identificando...') {
  if (!button) return;
  if (isLoading) {
    button.dataset.originalContent = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<i class="fas fa-spinner fa-spin"></i> <span>${loadingText}</span>`;
  } else {
    if (button.dataset.originalContent) button.innerHTML = button.dataset.originalContent;
    button.disabled = false;
  }
}

// ===== Inicialização =====
document.addEventListener("DOMContentLoaded", () => {
  initApp();
});

// No arquivo script.js, substitua a função initApp por esta versão corrigida
async function initApp() {
  try {
    cacheDOMElements();
    setupEventListeners();

    DOM.apiUrl.value = CONFIG.BASE_URL;
    await loadProducts();
    updateStats();
    await testConnection();
    await loadDashboardData();

    showPage('dashboard');
    Logger.log("Aplicação inicializada com sucesso", "success");
  } catch (error) {
    Logger.log(`Erro na inicialização: ${error.message}`, "error");
  }
}


// Remova qualquer outra referência à função setupNavigation que possa existir

function cacheDOMElements() {
  const ids = [
    "sidebar", "sidebarOverlay", "apiUrl", "btnMenu", "dropArea", "fileInput",
    "imagePreview", "btnIdentify", "btnRemoveImage", "uploadStatus", "aiStatus",
    "productForm", "productName", "productBrand", "productGTIN", "productCategory",
    "productNCM", "productCEST", "productPrice", "productsContainer", "totalProducts",
    "totalAI", "filterCategory", "filterBrand", "filterSort", "productsPagination",
    "paginationInfo", "btnPrevPage", "btnNextPage", "logsContent", "btnClearLogs",
    "connectionStatus", "notification-container",
    // Elementos da câmera adicionados aqui
    "btnOpenCamera", "cameraOverlay", "cameraFeed", "cameraCanvas", "cameraSnap", "cameraCancel"
  ];
  ids.forEach(id => {
    const camelCaseId = id.replace(/-([a-z])/g, g => g[1].toUpperCase());
    DOM[camelCaseId] = $(`#${id}`);
  });
  DOM.navLinks = $$(".nav-link");
  DOM.pageContents = $$(".page-content");
}

// Para evitar que gráficos antigos fiquem na memória
let categoryChartInstance = null;
let performanceChartInstance = null;
let productsPerPeriodChartInstance = null; // Adicione esta linha

// script.js

// ... (código existente, incluindo a declaração da variável performanceChartInstance) ...

// Substitua a função loadDashboardData inteira por esta
// No arquivo script.js, substitua a função loadDashboardData inteira
async function loadDashboardData() {
  // Estado inicial de carregamento com esqueleto
  const activityContainer = $("#recentActivity");
  if (activityContainer) {
    activityContainer.innerHTML = `
      <ul class="activity-feed-skeleton">
        <li></li><li></li><li></li><li></li>
      </ul>`;
  }

  try {
    const response = await fetch(`${CONFIG.BASE_URL}/dashboard/summary`);
    if (!response.ok) throw new Error("Falha ao carregar dados do dashboard");

    const data = await response.json();

    const appColors = {
      primary: 'rgba(0, 0, 255, 0.8)',
      primaryLight: 'rgba(0, 0, 255, 0.5)',
      accent: 'rgba(124, 124, 255, 0.8)',
      muted: 'rgba(77, 77, 77, 0.3)', // Cor mais suave para grid
      success: 'rgba(34, 197, 94, 0.8)',
      warning: 'rgba(245, 158, 11, 0.8)',
      text: '#333'
    };
    const categoryColors = [appColors.primary, appColors.accent, '#14b8a6', '#6b7280', appColors.warning, appColors.success];

    // --- 1. Atualizar Cards de KPIs ---
    $("#totalProducts").textContent = data.kpis.total_products;
    $("#totalAI").textContent = data.kpis.successful_identifications;
    $("#successRate").textContent = `${data.kpis.success_rate}%`;
    $("#avgTime").textContent = `${data.kpis.average_processing_time}s`;

    // Opções globais para os gráficos para um visual consistente
    const globalChartOptions = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: {
            font: { family: "'Montserrat', sans-serif", size: 12 },
            color: appColors.text,
            boxWidth: 12,
            padding: 15,
          }
        },
        tooltip: {
          enabled: true,
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          titleFont: { family: "'Montserrat', sans-serif", size: 14, weight: 'bold' },
          bodyFont: { family: "'Montserrat', sans-serif", size: 12 },
          padding: 10,
          cornerRadius: 4,
          boxPadding: 4,
        }
      },
      scales: {
        x: {
          ticks: { color: appColors.text, font: { family: "'Montserrat', sans-serif" } },
          grid: { display: false }
        },
        y: {
          ticks: { color: appColors.text, font: { family: "'Montserrat', sans-serif" } },
          grid: { color: appColors.muted, borderDash: [2, 4] }
        }
      }
    };

    // --- 2. Gráfico de Pizza (Produtos por Categoria) ---
    const categoryCtx = document.getElementById('categoryChart').getContext('2d');
    if (categoryChartInstance) categoryChartInstance.destroy();
    categoryChartInstance = new Chart(categoryCtx, {
      type: 'pie',
      data: {
        labels: data.category_distribution.map(c => c.category),
        datasets: [{
          data: data.category_distribution.map(c => c.count),
          backgroundColor: categoryColors,
          borderColor: 'var(--surface)',
          borderWidth: 3
        }]
      },
      options: { ...globalChartOptions, plugins: { ...globalChartOptions.plugins, legend: { ...globalChartOptions.plugins.legend, position: 'right' } } }
    });

    // --- 3. Gráfico de Linha (Histórico de Performance) ---
    const performanceCtx = document.getElementById('performanceChart').getContext('2d');
    if (performanceChartInstance) performanceChartInstance.destroy();
    performanceChartInstance = new Chart(performanceCtx, {
      type: 'line',
      data: {
        labels: data.performance_history.map(item => new Date(item.date).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })),
        datasets: [{
          label: 'Taxa de Sucesso (%)',
          data: data.performance_history.map(item => item.success_rate),
          borderColor: appColors.success,
          backgroundColor: 'rgba(34, 197, 94, 0.1)',
          fill: true,
          tension: 0.4,
          pointBackgroundColor: appColors.success,
          pointRadius: 4,
          pointHoverRadius: 6,
        }, {
          label: 'Tempo Médio (s)',
          data: data.performance_history.map(item => item.avg_time),
          borderColor: appColors.accent,
          backgroundColor: 'rgba(124, 124, 255, 0.1)',
          fill: true,
          tension: 0.4,
          pointBackgroundColor: appColors.accent,
          pointRadius: 4,
          pointHoverRadius: 6,
        }]
      },
      options: { ...globalChartOptions, plugins: { ...globalChartOptions.plugins, legend: { ...globalChartOptions.plugins.legend, position: 'top', align: 'end' } } }
    });

    // --- 4. Gráfico de Barras (Cadastros por Período) ---
    const productsPerPeriodCtx = document.getElementById('productsPerPeriodChart').getContext('2d');
    if (productsPerPeriodChartInstance) productsPerPeriodChartInstance.destroy();
    productsPerPeriodChartInstance = new Chart(productsPerPeriodCtx, {
      type: 'bar',
      data: {
        labels: data.products_per_day.map(item => new Date(item.period + 'T00:00:00').toLocaleDateString('pt-BR', { weekday: 'short' })),
        datasets: [{
          label: 'Produtos Cadastrados',
          data: data.products_per_day.map(item => item.count),
          backgroundColor: appColors.primaryLight,
          borderColor: appColors.primary,
          borderWidth: 1,
          borderRadius: 4,
          barThickness: 15
        }]
      },
      options: { ...globalChartOptions, plugins: { ...globalChartOptions.plugins, legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } }
    });

    // --- 5. Feed de Atividade Recente (usando classes CSS) ---
    if (data.recent_activities && data.recent_activities.length > 0) {
      const activityHTML = data.recent_activities.map(act => {
        const statusClass = act.success ? 'success' : 'failure';
        const icon = act.success ? 'fa-check-circle' : 'fa-exclamation-circle';
        const date = new Date(act.created_at).toLocaleString('pt-BR');
        return `
          <li>
            <i class="fas ${icon} activity-icon ${statusClass}"></i>
            <span>Análise com <strong>${statusClass === 'success' ? 'sucesso' : 'falha'}</strong></span>
            <span class="activity-date">${date}</span>
          </li>`;
      }).join('');
      activityContainer.innerHTML = `<div class="activity-feed"><ul>${activityHTML}</ul></div>`;
    } else {
      activityContainer.innerHTML = '<p class="muted text-center">Nenhuma atividade recente.</p>';
    }

  } catch (error) {
    Logger.log(`Erro no dashboard: ${error.message}`, 'error');
    if (activityContainer) {
      activityContainer.innerHTML = '<p class="muted text-center alert-error">Falha ao carregar atividades.</p>';
    }
  }
}

// ... (código restante do script.js) ...

function setupEventListeners() {
  // Navegação
  DOM.navLinks.forEach(link => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      const pageId = link.getAttribute("href").substring(1);
      showPage(pageId);
    });
  });

  DOM.btnMenu?.addEventListener("click", () => toggleSidebar(true));
  DOM.sidebarOverlay?.addEventListener("click", () => toggleSidebar(false));

  // Upload de imagem
  if (DOM.dropArea) {
    ["dragenter", "dragover", "dragleave", "drop"].forEach(eventName => {
      DOM.dropArea.addEventListener(eventName, preventDefaults);
    });

    DOM.dropArea.addEventListener("dragenter", () => DOM.dropArea.classList.add("drag"));
    DOM.dropArea.addEventListener("dragleave", () => DOM.dropArea.classList.remove("drag"));
    DOM.dropArea.addEventListener("drop", handleDrop);
    DOM.dropArea.addEventListener("click", () => DOM.fileInput.click());
  }

  DOM.fileInput?.addEventListener("change", (e) => handleFiles(e.target.files));
  DOM.btnIdentify?.addEventListener("click", processImageWithAI);
  DOM.btnRemoveImage?.addEventListener("click", resetIdentifyUI);

  // --- AQUI ESTÁ A ADIÇÃO PARA A CÂMERA ---
  DOM.btnOpenCamera?.addEventListener('click', openCamera);
  DOM.cameraSnap?.addEventListener('click', snapPhoto);
  DOM.cameraCancel?.addEventListener('click', closeCamera);
  // -----------------------------------------

  // Formulário
  DOM.productForm?.addEventListener("submit", saveProduct);

  // Logs
  DOM.btnClearLogs?.addEventListener("click", Logger.clear);

  // Filtros da Página de Produtos
  DOM.filterCategory?.addEventListener('change', () => loadProducts(1));
  DOM.filterBrand?.addEventListener('input', debounce(() => loadProducts(1), 500));
  DOM.filterSort?.addEventListener('change', () => loadProducts(1));

  // Configurações
  $("#btnSaveSettings")?.addEventListener("click", saveSettings);

  // Busca de produtos
  const searchInput = $("#searchProducts");
  if (searchInput) {
    searchInput.addEventListener("input", debounce(searchProducts, CONFIG.DEBOUNCE_DELAY));
  }

  // Dropdown de Exportação
  const exportContainer = $('#exportContainer');
  if (exportContainer) {
    const exportButton = $('#btnExport');
    const exportMenu = $('#exportMenu');

    exportButton.addEventListener('click', () => {
      exportContainer.classList.toggle('open');
      exportMenu.classList.toggle('visible');
    });

    $$('.dropdown-item', exportMenu).forEach(item => {
      item.addEventListener('click', (e) => {
        e.preventDefault();
        const format = item.dataset.format;
        exportProducts(format);
      });
    });

    document.addEventListener('click', (e) => {
      if (!exportContainer.contains(e.target)) {
        exportContainer.classList.remove('open');
        exportMenu.classList.remove('visible');
      }
    });
    // Listener para o botão de refresh do dashboard
    $("#btnRefreshDashboard")?.addEventListener("click", async (e) => {
      const button = e.currentTarget;
      const icon = button.querySelector('i');

      icon.classList.add('refreshing'); // Adiciona classe para animação
      button.disabled = true;

      await loadDashboardData();

      // Pequeno delay para o usuário perceber a atualização
      setTimeout(() => {
        icon.classList.remove('refreshing');
        button.disabled = false;
      }, 500);
    });
  }
}
// ===== Navegação =====
function toggleSidebar(open) {
  DOM.sidebar.classList.toggle("open", open);
  DOM.sidebarOverlay.classList.toggle("active", open);
  document.body.style.overflow = open ? "hidden" : "";
}

function showPage(pageId) {
  // Atualizar navegação
  DOM.navLinks.forEach(l => l.classList.remove("active"));
  $(`.nav-link[href="#${pageId}"]`)?.classList.add("active");

  // Mostrar página correspondente
  DOM.pageContents.forEach(page => page.style.display = "none");
  $(`#${pageId}`).style.display = "block";

  // Ações específicas por página
  if (pageId === "products") {
    renderProducts();
  } else if (pageId === "logs") {
    DOM.logsContent.scrollTop = DOM.logsContent.scrollHeight;
  }

  STATE.currentPage = pageId;
  Logger.log(`Navegando para: ${pageId}`);

  // Fechar sidebar no mobile
  if (window.innerWidth <= 960) {
    toggleSidebar(false);
  }
}

// ===== Upload e Processamento de Imagem =====
function preventDefaults(e) {
  e.preventDefault();
  e.stopPropagation();
}

function handleDrop(e) {
  const dt = e.dataTransfer;
  const files = dt.files;
  handleFiles(files);
}

function handleFiles(files) {
  if (!files || files.length === 0) return;

  const file = files[0];

  // Validar tipo de arquivo
  if (!CONFIG.SUPPORTED_FORMATS.includes(file.type)) {
    Logger.log("Formato de arquivo não suportado. Use JPEG, PNG, WebP, BMP ou GIF.", "error");
    showNotification("Formato de arquivo não suportado", "error");
    return;
  }

  // Validar tamanho do arquivo
  if (file.size > CONFIG.MAX_FILE_SIZE) {
    Logger.log("Arquivo muito grande. O tamanho máximo é 10MB.", "error");
    showNotification("Arquivo muito grande (máx. 10MB)", "error");
    return;
  }

  STATE.lastImageFile = file;
  DOM.btnIdentify.disabled = false;
  DOM.btnRemoveImage.style.display = "inline-flex";
  DOM.uploadStatus.textContent = `Imagem carregada: ${file.name} (${formatFileSize(file.size)})`;

  // Pré-visualização da imagem
  const reader = new FileReader();
  reader.onload = (e) => {
    DOM.imagePreview.src = e.target.result;
    DOM.imagePreview.style.display = "block";
  };
  reader.readAsDataURL(file);

  updateAIStatus("Pronto para análise", "info");
  Logger.log(`Imagem carregada: ${file.name}`, "success");
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + " bytes";
  else if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
  else return (bytes / 1048576).toFixed(1) + " MB";
}

async function processImageWithAI() {
  if (!STATE.lastImageFile) {
    Logger.log("Nenhuma imagem selecionada para análise.", "warning");
    return;
  }

  // Pega o elemento do botão para facilitar a leitura
  const identifyButton = DOM.btnIdentify;

  // --- INÍCIO DA MUDANÇA ---
  // 1. Ativa o estado de carregamento ANTES de iniciar o processo
  setButtonLoadingState(identifyButton, true, 'Identificando...');
  updateAIStatus("Analisando imagem...", "processing");
  // --- FIM DA MUDANÇA ---

  try {
    const formData = new FormData();
    formData.append("image", STATE.lastImageFile);

    const response = await fetch(`${CONFIG.BASE_URL}/vision/identify`, {
      method: "POST",
      body: formData
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.detail || result.message || `Erro ${response.status}`);
    }
    // --- INÍCIO DA NOVA LÓGICA PARA DUPLICATAS ---
    // Em frontend/js/script.js, dentro de processImageWithAI

    // --- INÍCIO DA LÓGICA CORRIGIDA PARA DUPLICATAS ---
    if (result.status === "duplicate_found") {
      // Chama o novo modal profissional e aguarda a resposta
      const userWantsToLoad = await showConfirmModal({
        title: "Imagem Duplicada",
        message: "Esta imagem já foi processada e salva anteriormente.<br>Deseja carregar os dados encontrados?",
        okText: "Sim, Carregar",
        okClass: "btn-primary" // Botão verde para confirmar
      });

      if (userWantsToLoad) {
        fillFormWithAIResults(result);
        updateAIStatus("Dados carregados do histórico", "success");
        Logger.log("Dados de imagem duplicada carregados.", "info");
      } else {
        updateAIStatus("Análise cancelada pelo usuário", "info");
        Logger.log("Usuário cancelou o carregamento de dados duplicados.", "info");
      }

      // A função termina aqui, pois não há mais nada a fazer.
      return;
    }
    // --- FIM DA LÓGICA CORRIGIDA ---
    // --- FIM DA NOVA LÓGICA ---
    if (result.success === false) {
      updateAIStatus(result.error_message || "Falha na análise", "error");
      Logger.log(`Análise falhou: ${result.error_message || "Erro desconhecido"}`, "error");
      return; // A execução para aqui, mas o 'finally' ainda será chamado
    }

    STATE.lastAIResult = result;
    STATE.lastImageHash = result.image_hash; // Adicione esta linha
    const confidencePercent = Math.round((result.confidence || 0) * 100);
    updateAIStatus(`Análise concluída (${confidencePercent}% confiança)`, "success");
    fillFormWithAIResults(result);
    Logger.log(`Produto identificado: ${result.product?.title || "Desconhecido"}`, "success");

  } catch (error) {
    updateAIStatus("Falha na análise", "error");
    Logger.log(`Erro na identificação: ${error.message}`, "error");
    showNotification(`Erro na análise: ${error.message}`, "error");
  } finally {
    // --- INÍCIO DA MUDANÇA ---
    // 2. Desativa o estado de carregamento DEPOIS que tudo terminou (sucesso ou falha)
    setButtonLoadingState(identifyButton, false);
    // --- FIM DA MUDANÇA ---
  }
}
function updateAIStatus(message, status) {
  if (!DOM.aiStatus) return;

  const icons = {
    processing: "spinner fa-spin",
    success: "check-circle",
    error: "exclamation-circle",
    warning: "exclamation-triangle",
    info: "info-circle"
  };

  DOM.aiStatus.innerHTML = `<i class="fas fa-${icons[status] || 'info-circle'}"></i> ${message}`;
  DOM.aiStatus.className = `chip ${status}`;
}

// Em frontend/js/script.js

function fillFormWithAIResults(result) {
  // Função auxiliar para definir o valor e a classe de um campo
  const setFieldValue = (element, value) => {
    const formGroup = element.closest('.form-group');

    // Primeiro, sempre limpa o estado anterior
    element.classList.remove('ai-filled');
    if (formGroup) {
      formGroup.classList.remove('ai-filled-group'); // Remove a classe do grupo também
    }

    if (value !== null && value !== undefined && value !== "") {
      // Define o valor e adiciona as classes de destaque
      element.value = value;
      element.classList.add('ai-filled');
      if (formGroup) {
        formGroup.classList.add('ai-filled-group');
      }

      // --- ADIÇÃO CRÍTICA PARA CORRIGIR O BUG DO SELECT ---
      // Se o elemento for um SELECT, vamos forçar a seleção da option correta.
      if (element.tagName === 'SELECT') {
        // Percorre todas as <option> dentro do <select>
        for (let i = 0; i < element.options.length; i++) {
          if (element.options[i].value === value) {
            // Define explicitamente esta opção como a selecionada
            element.options[i].selected = true;
            break; // Para a busca assim que encontrar
          }
        }
      }
      // --- FIM DA ADIÇÃO ---

    } else {
      // Se não houver valor, limpa o campo
      element.value = '';
    }
  };

  const product = result.product || {};

  // Usa a função auxiliar para cada campo do formulário
  setFieldValue(DOM.productName, product.title);
  setFieldValue(DOM.productBrand, product.brand);
  setFieldValue(DOM.productGTIN, product.gtin);
  setFieldValue(DOM.productCategory, product.category);
  setFieldValue(DOM.productNCM, product.ncm);
  setFieldValue(DOM.productCEST, product.cest);
  setFieldValue(DOM.productPrice, product.price);

  // Foca no primeiro campo vazio ou no preço (lógica original mantida)
  if (!DOM.productName.value) {
    DOM.productName.focus();
  } else if (!DOM.productPrice.value) {
    DOM.productPrice.focus();
  }
}

function resetIdentifyUI() {
  STATE.lastImageFile = null;
  STATE.lastAIResult = null;
  DOM.imagePreview.style.display = "none";
  DOM.imagePreview.src = "";
  DOM.btnIdentify.disabled = true;
  DOM.btnRemoveImage.style.display = "none";
  DOM.uploadStatus.textContent = "Aguardando imagem...";
  DOM.productForm.reset();
  // --- ADIÇÃO IMPORTANTE ---
  // Percorre todos os campos do formulário e remove a classe de destaque.
  const formElements = DOM.productForm.querySelectorAll('input, select');
  formElements.forEach(el => el.classList.remove('ai-filled'));
  // --- FIM DA ADIÇÃO ---

  updateAIStatus("Aguardando análise", "info");
  Logger.log("Imagem removida", "info");
}

// ===== Gerenciamento de Estado de Loading =====
function setLoadingState(element, isLoading, text = "") {
  if (!element) return;

  if (isLoading) {
    element.disabled = true;
    element.innerHTML = text.includes("spinner") ? text : `<div class="spinner"></div> ${text}`;
    STATE.isLoading = true;
  } else {
    element.disabled = false;
    element.innerHTML = text;
    STATE.isLoading = false;
  }
}

// ===== Gerenciamento de Produtos =====

// SUBSTITUA A FUNÇÃO ANTIGA POR ESTA
async function deleteProduct(productId, productTitle) {
  const confirmed = await showConfirmModal({
    title: "Confirmar Exclusão",
    message: `Você tem certeza que deseja excluir o produto <strong>"${productTitle}"</strong>?<br>Esta ação não pode ser desfeita.`,
    okText: "Sim, Excluir",
    okClass: "btn-danger"
  });

  if (!confirmed) {
    return; // O usuário cancelou
  }

  try {
    const response = await fetch(`${CONFIG.BASE_URL}/products/${productId}`, {
      method: 'DELETE'
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || 'Erro ao excluir o produto.');
    }

    // Remove a linha da tabela da interface para feedback imediato
    const row = document.getElementById(`product-row-${productId}`);
    if (row) {
      row.style.transition = 'opacity 0.3s ease';
      row.style.opacity = '0';
      setTimeout(() => row.remove(), 300);
    }

    // Atualiza os dados de fundo
    STATE.products = STATE.products.filter(p => p.id !== productId);
    updateStats();
    showNotification("Produto excluído com sucesso!", "success");

  } catch (error) {
    Logger.log(`Erro ao excluir produto: ${error.message}`, "error");
    showNotification(error.message, "error");
  }
}

async function exportProducts(format = 'csv') {
  const exportButton = $('#btnExport');
  if (!exportButton) return;

  const originalContent = exportButton.innerHTML;
  setButtonLoadingState(exportButton, true, `Gerando .${format}...`);

  try {
    const category = DOM.filterCategory?.value || "";
    const brand = DOM.filterBrand?.value.trim() || "";
    const sort = DOM.filterSort?.value || "newest";

    const params = new URLSearchParams();
    if (category) params.append('category', category);
    if (brand) params.append('brand', brand);
    params.append('sort', sort);
    params.append('format', format);

    const url = `${CONFIG.BASE_URL}/products/export?${params.toString()}`;
    Logger.log(`Iniciando exportação para: ${url}`, "info");

    const response = await fetch(url);

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Erro ${response.status}: ${errorText}`);
    }

    const blob = await response.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = downloadUrl;
    const extension = format === 'excel' ? 'xlsx' : 'csv';
    a.download = `cadvision_produtos_${new Date().toISOString().slice(0, 10)}.${extension}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(downloadUrl);

    Logger.log("Exportação concluída com sucesso.", "success");
    showNotification("Relatório de produtos gerado!", "success");

  } catch (error) {
    Logger.log(`Falha na exportação: ${error.message}`, "error");
    showNotification(`Erro na exportação: ${error.message}`, "error");
  } finally {
    setButtonLoadingState(exportButton, false);
    exportButton.innerHTML = originalContent;
  }
}

async function saveProduct(e) {
  e.preventDefault();

  const productData = {
    title: DOM.productName.value.trim(),
    brand: DOM.productBrand.value.trim() || null,
    gtin: DOM.productGTIN.value.trim() || null,
    confidence: STATE.lastAIResult?.confidence || null,
    image_hash: STATE.lastImageHash || null, // Adiciona o hash da imagem
    category: DOM.productCategory.value.trim() || null,
    price: DOM.productPrice.value ? parseFloat(DOM.productPrice.value.replace(',', '.')) : null,
    ncm: DOM.productNCM.value.trim() || null,
    cest: DOM.productCEST.value.trim() || null,
    confidence: STATE.lastAIResult?.confidence || null
  };

  if (!productData.title) {
    showNotification("O título do produto é obrigatório.", "error");
    DOM.productName.focus();
    return;
  }

  setLoadingState(DOM.productForm.querySelector('button[type="submit"]'), true, "Salvando...");

  try {
    const response = await fetch(`${CONFIG.BASE_URL}/products`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(productData)
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.detail || result.message || `Erro ${response.status}`);
    }

    Logger.log(`Produto salvo: ${productData.title}`, "success");
    showNotification("Produto salvo com sucesso!", "success");

    resetIdentifyUI();
    await loadProducts();
    showPage('products');

  } catch (error) {
    Logger.log(`Erro ao salvar produto: ${error.message}`, "error");
    showNotification(`Erro ao salvar: ${error.message}`, "error");
  } finally {
    setLoadingState(DOM.productForm.querySelector('button[type="submit"]'), false, "Salvar Produto");
  }
}

// Em frontend/js/script.js, substitua a função loadProducts
// Em frontend/js/script.js, adicione esta nova função

async function openEditModal(productId) {
  const overlay = $('#editOverlay');
  const form = $('#editProductForm');
  if (!overlay || !form) return;

  try {
    // 1. Busca os dados atuais do produto no backend
    const response = await fetch(`${CONFIG.BASE_URL}/products/${productId}`);
    if (!response.ok) throw new Error("Produto não encontrado.");

    const product = await response.json();

    // 2. Constrói o HTML do formulário e o preenche com os dados
    form.innerHTML = `
      <input type="hidden" id="editProductId" value="${product.id}">
      <div class="form-group" style="grid-column: 1 / -1;">
        <label for="editProductName">Nome do Produto *</label>
        <input type="text" id="editProductName" value="${escapeHtml(product.title)}" required>
      </div>
      <div class="form-group">
        <label for="editProductBrand">Marca</label>
        <input type="text" id="editProductBrand" value="${escapeHtml(product.brand || '')}">
      </div>
      <div class="form-group">
        <label for="editProductCategory">Categoria</label>
        <select id="editProductCategory">
          <option value="Alimentos">Alimentos</option>
          <option value="Bebidas">Bebidas</option>
          <option value="Limpeza">Limpeza</option>
          <option value="Higiene">Higiene</option>
          <option value="Eletrônicos">Eletrônicos</option>
          <option value="Outros">Outros</option>
        </select>
      </div>
      <div class="form-group">
        <label for="editProductGTIN">GTIN/EAN</label>
        <input type="text" id="editProductGTIN" value="${escapeHtml(product.gtin || '')}">
      </div>
      <div class="form-group">
        <label for="editProductNCM">NCM</label>
        <input type="text" id="editProductNCM" value="${escapeHtml(product.ncm || '')}">
      </div>
      <div class="form-group">
        <label for="editProductPrice">Preço (R$)</label>
        <input type="number" step="0.01" id="editProductPrice" value="${product.price || ''}">
      </div>
      <div class="modal-footer" style="grid-column: 1 / -1;">
        <button type="button" class="btn btn-secondary" id="editCancel">Cancelar</button>
        <button type="submit" class="btn btn-primary">Salvar Alterações</button>
      </div>
    `;

    // 3. Seleciona a categoria correta no dropdown
    $('#editProductCategory').value = product.category;

    // 4. Mostra o modal
    overlay.style.display = 'flex';
    setTimeout(() => overlay.classList.add('visible'), 10);

    // 5. Adiciona os event listeners para os botões do modal
    $('#editCancel').addEventListener('click', () => closeEditModal());
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeEditModal();
    });
    form.addEventListener('submit', handleUpdateProduct);

  } catch (error) {
    Logger.log(`Erro ao abrir modal de edição: ${error.message}`, "error");
  }
}

function closeEditModal() {
  const overlay = $('#editOverlay');
  if (!overlay) return;
  overlay.classList.remove('visible');
  setTimeout(() => overlay.style.display = 'none', 300);
}

// Em frontend/js/script.js, adicione esta nova função

async function handleUpdateProduct(e) {
  e.preventDefault();
  const productId = $('#editProductId').value;
  const submitButton = e.target.querySelector('button[type="submit"]');

  const productData = {
    title: $('#editProductName').value.trim(),
    brand: $('#editProductBrand').value.trim(),
    category: $('#editProductCategory').value,
    gtin: $('#editProductGTIN').value.trim(),
    ncm: $('#editProductNCM').value.trim(),
    price: parseFloat($('#editProductPrice').value) || null
  };

  setButtonLoadingState(submitButton, true, "Salvando...");

  try {
    const response = await fetch(`${CONFIG.BASE_URL}/products/${productId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(productData)
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || "Falha ao atualizar produto.");
    }

    showNotification("Produto atualizado com sucesso!", "success");
    closeEditModal();
    await loadProducts(); // Recarrega a lista para mostrar as alterações

  } catch (error) {
    Logger.log(`Erro ao atualizar produto: ${error.message}`, "error");
  } finally {
    setButtonLoadingState(submitButton, false);
  }
}

// Em frontend/js/script.js, substitua a função loadProducts inteira por esta

async function loadProducts(page = 1) {
  try {
    DOM.productsContainer.innerHTML = `<div class="card text-center muted">Carregando produtos...</div>`;

    // 1. Pega os valores atuais dos filtros E DA ORDENAÇÃO
    const category = DOM.filterCategory?.value || "";
    const brand = DOM.filterBrand?.value.trim() || "";
    const sort = DOM.filterSort?.value || "newest"; // Pega o valor da ordenação

    // 2. Monta a URL com TODOS os parâmetros, incluindo 'sort'
    const params = new URLSearchParams({
      page: page,
      size: 10,
      sort: sort // <-- CORREÇÃO APLICADA AQUI
    });
    if (category) params.append('category', category);
    if (brand) params.append('brand', brand);

    const url = `${CONFIG.BASE_URL}/products?${params.toString()}`;
    Logger.log(`Carregando produtos de: ${url}`, "info");

    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Erro HTTP ${response.status}`);
    }

    const result = await response.json();

    STATE.products = result.items || [];
    renderProducts();

    // Atualiza a informação da paginação
    if (DOM.paginationInfo) {
      DOM.paginationInfo.textContent = `Página ${result.page} de ${result.pages}`;
      DOM.productsPagination.style.display = result.pages > 1 ? 'flex' : 'none';
    }

  } catch (error) {
    Logger.log(`Erro ao carregar produtos: ${error.message}`, "error");
    DOM.productsContainer.innerHTML = `<div class="card text-center alert-error">Falha ao carregar produtos.</div>`;
  }
}

// Em frontend/js/script.js

function renderProducts() {
  if (!DOM.productsContainer) return;

  if (STATE.products.length === 0) {
    DOM.productsContainer.innerHTML = `
      <div class="card text-center">
        <i class="fas fa-box-open" style="font-size: 48px; color: var(--muted); margin-bottom: 15px;"></i>
        <p class="muted">Nenhum produto cadastrado ainda.</p>
        <button class="btn btn-primary" onclick="showPage('identify')">
          <i class="fas fa-robot"></i> Identificar Primeiro Produto
        </button>
      </div>`;
    return;
  }

  const tableHTML = `
    <div class="products-table-container card p-0">
      <table class="table-products">
        <thead>
          <tr>
            <th>Produto</th>
            <th>Marca</th>
            <th>Categoria</th>
            <th>GTIN/EAN</th>
            <th>Cadastrado em</th>
            <th class="text-center">Ações</th>
          </tr>
        </thead>
        <tbody>
          ${STATE.products.map(product => `
            <tr id="product-row-${product.id}">
              <td data-label="Produto" class="product-title">
                ${escapeHtml(product.title)}
                ${product.confidence ? `<span class="badge badge-primary">${Math.round(product.confidence * 100)}%</span>` : ''}
              </td>
              <td data-label="Marca">${escapeHtml(product.brand || 'N/A')}</td>
              <td data-label="Categoria">${escapeHtml(product.category || 'N/A')}</td>
              <td data-label="GTIN/EAN" class="mono">${escapeHtml(product.gtin || 'N/A')}</td>
              <td data-label="Cadastrado em">${new Date(product.created_at).toLocaleDateString('pt-BR')}</td>
              <td class="actions">
                <button class="btn btn-secondary btn-sm btn-edit" data-id="${product.id}" title="Editar">
                  <i class="fas fa-pencil-alt"></i>
                </button>
                <button class="btn btn-danger btn-sm btn-delete" data-id="${product.id}" data-title="${escapeHtml(product.title)}" title="Excluir">
                  <i class="fas fa-trash"></i>
                </button>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>`;

  DOM.productsContainer.innerHTML = tableHTML;

  // Chama a nova função para ativar os botões
  setupProductEventListeners();
}

function setupProductEventListeners() {
  // Adiciona o evento de clique para todos os botões de editar
  $$('.btn-edit').forEach(button => {
    button.addEventListener('click', (e) => {
      // Pega o ID diretamente do atributo data-id do botão
      const productId = e.currentTarget.dataset.id;
      openEditModal(productId);
    });
  });

  // Adiciona o evento de clique para todos os botões de deletar
  $$('.btn-delete').forEach(button => {
    button.addEventListener('click', (e) => {
      // Pega o ID e o Título diretamente dos atributos do botão
      const productId = e.currentTarget.dataset.id;
      const productTitle = e.currentTarget.dataset.title;
      deleteProduct(productId, productTitle);
    });
  });
}

function escapeHtml(text) {
  if (text === null || typeof text === 'undefined') return '';
  return text.toString()
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function updateStats() {
  if (DOM.totalProducts) {
    DOM.totalProducts.textContent = STATE.products.length;
  }
  if (DOM.totalAI) {
    // CORRIGIDO: Agora o valor é calculado corretamente
    const aiCount = STATE.products.filter(p => p.confidence > 0).length;
    DOM.totalAI.textContent = aiCount;
  }
}

function searchProducts() {
  const searchTerm = $("#searchProducts").value.toLowerCase();
  if (!searchTerm) {
    renderProducts();
    return;
  }

  const filteredProducts = STATE.products.filter(product =>
    product.title.toLowerCase().includes(searchTerm) ||
    (product.brand && product.brand.toLowerCase().includes(searchTerm)) ||
    (product.category && product.category.toLowerCase().includes(searchTerm)) ||
    (product.gtin && product.gtin.includes(searchTerm))
  );

  renderFilteredProducts(filteredProducts);
}

function renderFilteredProducts(products) {
  if (!DOM.productsContainer) return;

  if (products.length === 0) {
    DOM.productsContainer.innerHTML = `
      <div class="card text-center">
        <i class="fas fa-search" style="font-size: 48px; color: var(--muted); margin-bottom: 15px;"></i>
        <p class="muted">Nenhum produto encontrado.</p>
      </div>
    `;
    return;
  }

  DOM.productsContainer.innerHTML = products.map(product => `
    <div class="card fade-in">
      <h3>${escapeHtml(product.title)}</h3>
      <p><strong>Marca:</strong> ${product.brand || "N/A"}</p>
      <p><strong>Preço:</strong> ${product.price ? `R$ ${product.price.toFixed(2).replace('.', ',')}` : "N/A"}</p>
      <p><strong>Categoria:</strong> ${product.category || "N/A"}</p>
      ${product.gtin ? `<p><strong>GTIN:</strong> ${product.gtin}</p>` : ''}
      ${product.confidence ? `<p><strong>Confiança da IA:</strong> ${Math.round(product.confidence * 100)}%</p>` : ''}
      <small class="muted">Cadastrado em: ${new Date(product.created_at).toLocaleString('pt-BR')}</small>
    </div>
  `).join('');
}

// ===== Teste de Conexão =====
async function testConnection() {
  if (!DOM.connectionStatus) return;

  try {
    const response = await fetch(`${CONFIG.BASE_URL}/health`);
    const result = await response.json();

    if (response.ok && result.status === "healthy") {
      DOM.connectionStatus.textContent = "Conectado";
      DOM.connectionStatus.style.color = "var(--success)";
      STATE.connectionStatus = "connected";
    } else {
      throw new Error(result.message || "Servidor não está saudável");
    }
  } catch (error) {
    DOM.connectionStatus.textContent = "Desconectado";
    DOM.connectionStatus.style.color = "var(--error)";
    STATE.connectionStatus = "disconnected";
    Logger.log(`Falha na conexão: ${error.message}`, "error");
  }
}

// ===== Configurações =====
function saveSettings() {
  const apiUrl = DOM.apiUrl.value.trim();

  if (!apiUrl) {
    showNotification("Por favor, informe uma URL válida para a API.", "error");
    return;
  }

  try {
    // Validar URL
    new URL(apiUrl);

    CONFIG.BASE_URL = apiUrl;
    localStorage.setItem("apiUrl", apiUrl);

    Logger.log(`URL da API atualizada para: ${apiUrl}`, "success");
    showNotification("Configurações salvas com sucesso!", "success");

    // Testar a nova conexão
    testConnection();
  } catch (error) {
    Logger.log("URL inválida fornecida", "error");
    showNotification("URL inválida. Por favor, verifique o formato.", "error");
  }
}

// ===== Utilitários de Exibição =====
function formatCurrency(value) {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL'
  }).format(value);
}

// Adicionar animação de entrada para notificações
const style = document.createElement('style');
style.textContent = `
  @keyframes slideInRight {
    from {
      transform: translateX(100%);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }
  
  @keyframes slideOutRight {
    from {
      transform: translateX(0);
      opacity: 1;
    }
    to {
      transform: translateX(100%);
      opacity: 0;
    }
  }
  
  .notification {
    animation: slideInRight 0.3s ease;
  }
  
  .notification.hiding {
    animation: slideOutRight 0.3s ease;
  }
`;
document.head.appendChild(style);

let cameraStream = null;

async function openCamera() {
  // 1. Verifica se o navegador tem suporte à API da câmera
  if (!('mediaDevices' in navigator && 'getUserMedia' in navigator.mediaDevices)) {
    showNotification("Seu navegador não suporta a funcionalidade de câmera.", "error");
    return;
  }

  try {
    // 2. Pede permissão e inicia a câmera
    const constraints = { video: { facingMode: "environment" } }; // Prefere a câmera traseira
    cameraStream = await navigator.mediaDevices.getUserMedia(constraints);

    // 3. (SUCESSO) Se a permissão for concedida, exibe o modal e a notificação
    showNotification("Câmera iniciada. Aponte para o produto.", "info");

    DOM.cameraFeed.srcObject = cameraStream;
    DOM.cameraOverlay.style.display = 'flex';
    setTimeout(() => DOM.cameraOverlay.classList.add('visible'), 10);

  } catch (err) {
    // 4. (ERRO) Se algo der errado, registra o erro e mostra uma notificação específica
    Logger.log(`Erro ao acessar a câmera: ${err.name}`, "error");

    let userMessage = "Ocorreu um erro desconhecido ao tentar acessar a câmera.";

    if (err.name === "NotAllowedError") {
      userMessage = "Permissão para acessar a câmera foi negada. Por favor, habilite nas configurações do seu navegador.";
    } else if (err.name === "NotFoundError") {
      userMessage = "Nenhuma câmera foi encontrada neste dispositivo.";
    }

    showNotification(userMessage, "error");
  }
}

function closeCamera() {
  if (cameraStream) {
    cameraStream.getTracks().forEach(track => track.stop()); // Para a câmera
  }
  DOM.cameraOverlay.classList.remove('visible');
  setTimeout(() => DOM.cameraOverlay.style.display = 'none', 300);
}

function snapPhoto() {
  const canvas = DOM.cameraCanvas;
  const video = DOM.cameraFeed;

  // Ajusta o tamanho do canvas para o tamanho do vídeo
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;

  // Desenha o frame atual do vídeo no canvas
  const context = canvas.getContext('2d');
  context.drawImage(video, 0, 0, canvas.width, canvas.height);

  // Converte o canvas para um arquivo (Blob)
  canvas.toBlob(blob => {
    // Cria um objeto File a partir do Blob
    const photoFile = new File([blob], `cadvision-capture-${Date.now()}.jpg`, { type: 'image/jpeg' });

    // **REUTILIZAÇÃO!** Passamos o arquivo para a mesma função que cuida do upload
    handleFiles([photoFile]);

    // Fecha a câmera
    closeCamera();

  }, 'image/jpeg');
}