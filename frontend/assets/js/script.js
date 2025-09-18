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
  currentPage: "identify",
  isLoading: false,
  connectionStatus: "checking",
};

// ===== Cache de Elementos DOM =====
const DOM = {
  // Será preenchido durante a inicialização
};

// ===== Utilitários =====
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// Sistema de logging melhorado
const Logger = {
  log: (message, type = "info") => {
    const timestamp = new Date().toLocaleTimeString();
    const logEntry = `[${timestamp}] ${type.toUpperCase()}: ${message}`;
    console.log(logEntry);

    const logsContent = $("#logsContent");
    if (logsContent) {
      logsContent.textContent += "\n" + logEntry;
      logsContent.scrollTop = logsContent.scrollHeight;
    }

    // Mostrar notificação visual para erros e sucessos
    if (type === "error" || type === "success") {
      showNotification(message, type);
    }
  },

  clear: () => {
    const logsContent = $("#logsContent");
    if (logsContent) logsContent.textContent = "";
  }
};

// Sistema de notificações
function showNotification(message, type = "info", duration = 5000) {
  const notification = document.createElement("div");
  notification.className = `notification notification-${type}`;
  notification.innerHTML = `
    <i class="fas fa-${getNotificationIcon(type)}"></i>
    <span>${message}</span>
    <button onclick="this.parentElement.remove()">
      <i class="fas fa-times"></i>
    </button>
  `;

  // Estilo para a notificação
  notification.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    background: ${getNotificationBgColor(type)};
    color: white;
    padding: 12px 16px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    gap: 10px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    z-index: 10000;
    max-width: 400px;
    animation: slideInRight 0.3s ease;
  `;

  document.body.appendChild(notification);

  // Remover automaticamente após a duração
  if (duration > 0) {
    setTimeout(() => {
      if (notification.parentElement) {
        notification.remove();
      }
    }, duration);
  }

  return notification;
}

function getNotificationIcon(type) {
  const icons = {
    success: "check-circle",
    error: "exclamation-circle",
    warning: "exclamation-triangle",
    info: "info-circle",
    loading: "spinner fa-spin"
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

// Debounce para melhor performance
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
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

    // Configura a navegação
    DOM.navLinks.forEach(link => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        const pageId = link.getAttribute("href").substring(1);
        showPage(pageId);
      });
    });

    DOM.btnMenu?.addEventListener("click", () => toggleSidebar(true));
    DOM.sidebarOverlay?.addEventListener("click", () => toggleSidebar(false));

    DOM.apiUrl.value = CONFIG.BASE_URL;
    await loadProducts();
    updateStats();
    await testConnection();

    showPage('identify');
    Logger.log("Aplicação inicializada com sucesso", "success");
  } catch (error) {
    Logger.log(`Erro na inicialização: ${error.message}`, "error");
  }
}

// Remova qualquer outra referência à função setupNavigation que possa existir

function cacheDOMElements() {
  // Elementos principais
  DOM.sidebar = $("#sidebar");
  DOM.sidebarOverlay = $("#sidebarOverlay");
  DOM.apiUrl = $("#apiUrl");

  // Navegação
  DOM.navLinks = $$(".nav-link");
  DOM.pageContents = $$(".page-content");
  DOM.btnMenu = $("#btnMenu");

  // Upload de imagem
  DOM.dropArea = $("#dropArea");
  DOM.fileInput = $("#fileInput");
  DOM.imagePreview = $("#imagePreview");
  DOM.btnIdentify = $("#btnIdentify");
  DOM.btnRemoveImage = $("#btnRemoveImage");
  DOM.uploadStatus = $("#uploadStatus");
  DOM.aiStatus = $("#aiStatus");

  // Formulário de produto
  DOM.productForm = $("#productForm");
  DOM.productName = $("#productName");
  DOM.productBrand = $("#productBrand");
  DOM.productGTIN = $("#productGTIN");
  DOM.productCategory = $("#productCategory");
  DOM.productNCM = $("#productNCM");
  DOM.productCEST = $("#productCEST");
  DOM.productPrice = $("#productPrice");

  // Lista de produtos
  DOM.productsContainer = $("#productsContainer");
  DOM.totalProducts = $("#totalProducts");
  DOM.totalAI = $("#totalAI");

  // Logs
  DOM.logsContent = $("#logsContent");
  DOM.btnClearLogs = $("#btnClearLogs");

  // Status de conexão
  DOM.connectionStatus = $("#connectionStatus");
}

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

  // Formulário
  DOM.productForm?.addEventListener("submit", saveProduct);

  // Logs
  DOM.btnClearLogs?.addEventListener("click", Logger.clear);

  // Configurações
  $("#btnSaveSettings")?.addEventListener("click", saveSettings);

  // Busca de produtos (se houver)
  const searchInput = $("#searchProducts");
  if (searchInput) {
    searchInput.addEventListener("input", debounce(searchProducts, CONFIG.DEBOUNCE_DELAY));
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
  if (!STATE.lastImageFile) return;

  updateAIStatus("Analisando imagem...", "processing");
  setLoadingState(DOM.btnIdentify, true, "Processando...");

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

    // Verificar se a API retornou a estrutura esperada
    if (result.success === false) {
      updateAIStatus(result.error_message || "Falha na análise", "error");
      Logger.log(`Análise falhou: ${result.error_message || "Erro desconhecido"}`, "error");
      return;
    }

    STATE.lastAIResult = result;
    const confidencePercent = Math.round((result.confidence || 0) * 100);
    updateAIStatus(`Análise concluída (${confidencePercent}% confiança)`, "success");
    fillFormWithAIResults(result);
    Logger.log(`Produto identificado: ${result.title || result.product?.title || "Desconhecido"}`, "success");

  } catch (error) {
    updateAIStatus("Falha na análise", "error");
    Logger.log(`Erro na identificação: ${error.message}`, "error");
    showNotification(`Erro na análise: ${error.message}`, "error");
  } finally {
    setLoadingState(DOM.btnIdentify, false, '<i class="fas fa-robot"></i> Identificar com IA');
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

function fillFormWithAIResults(result) {
  // Preenche o formulário com os dados da identificação
  // Usa valores padrão para campos vazios
  $("#productName").value = result.product?.title || "";
  $("#productBrand").value = result.product?.brand || "";
  $("#productGTIN").value = result.product?.gtin || "";
  $("#productCategory").value = result.product?.category || "";
  $("#productNCM").value = result.product?.ncm || "";
  $("#productCEST").value = result.product?.cest || "";
  $("#productPrice").value = result.product?.price || "";

  // Foca no primeiro campo vazio ou no preço
  if (!$("#productName").value) {
    $("#productName").focus();
  } else {
    $("#productPrice").focus();
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
async function saveProduct(e) {
  e.preventDefault();

  const productData = {
    title: DOM.productName.value.trim(),
    brand: DOM.productBrand.value.trim() || null,
    gtin: DOM.productGTIN.value.trim() || null,
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

async function loadProducts() {
  try {
    setLoadingState($("#btnRefreshProducts"), true, "Carregando...");

    const response = await fetch(`${CONFIG.BASE_URL}/products`);

    if (!response.ok) {
      throw new Error(`HTTP Error ${response.status}`);
    }

    const result = await response.json();

    // Verificar se a resposta é paginada
    STATE.products = result.items || result;
    Logger.log(`Carregados ${STATE.products.length} produtos`, "success");
    renderProducts();

  } catch (error) {
    Logger.log(`Erro ao carregar produtos: ${error.message}`, "error");
    showNotification("Erro ao carregar produtos", "error");
  } finally {
    setLoadingState($("#btnRefreshProducts"), false, "Atualizar Lista");
    updateStats();
  }
}

function renderProducts() {
  if (!DOM.productsContainer) return;

  if (STATE.products.length === 0) {
    DOM.productsContainer.innerHTML = `
      <div class="card text-center">
        <i class="fas fa-box-open" style="font-size: 48px; color: var(--muted); margin-bottom: 15px;"></i>
        <p class="muted">Nenhum produto cadastrado ainda.</p>
        <button class="btn btn-primary" onclick="showPage('identify')">
          <i class="fas fa-camera"></i> Identificar Primeiro Produto
        </button>
      </div>
    `;
    return;
  }

  DOM.productsContainer.innerHTML = STATE.products.map(product => `
    <div class="card fade-in">
      <div class="d-flex justify-content-between align-items-start">
        <h3 class="mt-0">${escapeHtml(product.title)}</h3>
        ${product.confidence ? `
          <span class="badge badge-primary">
            <i class="fas fa-robot"></i> ${Math.round(product.confidence * 100)}%
          </span>
        ` : ''}
      </div>
      
      <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 15px;">
        ${product.brand ? `
          <div>
            <strong>Marca:</strong>
            <p>${escapeHtml(product.brand)}</p>
          </div>
        ` : ''}
        
        ${product.category ? `
          <div>
            <strong>Categoria:</strong>
            <p>${escapeHtml(product.category)}</p>
          </div>
        ` : ''}
        
        ${product.price ? `
          <div>
            <strong>Preço:</strong>
            <p>R$ ${product.price.toFixed(2).replace('.', ',')}</p>
          </div>
        ` : ''}
      </div>
      
      <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
        ${product.gtin ? `
          <div>
            <strong>GTIN:</strong>
            <p class="mono">${escapeHtml(product.gtin)}</p>
          </div>
        ` : ''}
        
        ${product.ncm ? `
          <div>
            <strong>NCM:</strong>
            <p class="mono">${escapeHtml(product.ncm)}</p>
          </div>
        ` : ''}
        
        ${product.cest ? `
          <div>
            <strong>CEST:</strong>
            <p class="mono">${escapeHtml(product.cest)}</p>
          </div>
        ` : ''}
      </div>
      
      <small class="muted">Cadastrado em: ${new Date(product.created_at).toLocaleString('pt-BR')}</small>
    </div>
  `).join('');
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function updateStats() {
  if (DOM.totalProducts) DOM.totalProducts.textContent = STATE.products.length;
  if (DOM.totalAI) {
    const aiCount = STATE.products.filter(p => p.confidence).length;
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