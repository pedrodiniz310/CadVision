// ===== Estado global =====
const state = {
  baseUrl: localStorage.getItem("apiUrl") || "http://127.0.0.1:8000/api/v1",
  products: [], // Será carregado da API
  lastImageFile: null,
  lastAI: null,
  currentPage: "dashboard"
};

// ===== Helpers =====
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const log = (message, type = "info") => {
  const timestamp = new Date().toISOString().substring(11, 19);
  const logEntry = `[${timestamp}] ${type.toUpperCase()}: ${message}`;
  console.log(logEntry);

  // Atualizar logs na página
  if ($("#logsContent")) {
    $("#logsContent").textContent += "\n" + logEntry;
    $("#logsContent").scrollTop = $("#logsContent").scrollHeight;
  }
};

// ===== Inicialização =====
document.addEventListener("DOMContentLoaded", () => {
  initApp();
  setupEventListeners();
});

function initApp() {
  // Carregar produtos da API e depois atualizar o resto
  loadProducts().then(() => {
    updateStats();
    if (state.currentPage === "products") {
      renderProducts();
    }
  });

  // Configurar navegação
  $$(".nav-link").forEach(link => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      const page = link.getAttribute("href").substring(1);
      showPage(page);
      $$(".nav-link").forEach(l => l.classList.remove("active"));
      link.classList.add("active");

      // Fechar sidebar no mobile após clicar em um link
      if (window.innerWidth <= 960) {
        $("#sidebar").classList.remove("open");
        $("#sidebarOverlay").classList.remove("active");
      }
    });
  });

  // Menu mobile
  $("#btnMenu")?.addEventListener("click", () => {
    $("#sidebar").classList.toggle("open");
    $("#sidebarOverlay").classList.toggle("active");
  });

  // Fechar sidebar ao clicar no overlay
  $("#sidebarOverlay")?.addEventListener("click", () => {
    $("#sidebar").classList.remove("open");
    $("#sidebarOverlay").classList.remove("active");
  });

  // Configurar URL da API
  if ($("#apiUrl")) {
    $("#apiUrl").value = state.baseUrl;
  }

  // Testar conexão inicial
  setTimeout(testConnection, 2000);
  showPage('identify'); // Inicia na página de identificação
}

function showPage(pageId) {
  $$(".page-content").forEach(page => page.classList.remove("active"));
  $(`#${pageId}`)?.classList.add("active");
  state.currentPage = pageId;
  log(`Navegando para: ${pageId}`);

  // Atualizar conteúdo específico da página
  if (pageId === "products") {
    renderProducts();
  }
}

function updateStats() {
  if ($("#totalProducts")) {
    $("#totalProducts").textContent = state.products.length;
  }

  const aiCount = state.products.filter(p => p.confidence && p.confidence > 0).length;
  if ($("#totalAI")) {
    $("#totalAI").textContent = aiCount;
  }
}

// ===== Upload e Processamento de Imagem =====
function setupEventListeners() {
  const dropArea = $("#dropArea");
  const fileInput = $("#fileInput");

  if (dropArea) {
    ["dragenter", "dragover", "dragleave", "drop"].forEach(eventName => {
      dropArea.addEventListener(eventName, preventDefaults, false);
    });
    ["dragenter", "dragover"].forEach(eventName => {
      dropArea.addEventListener(eventName, () => dropArea.classList.add("drag"), false);
    });
    ["dragleave", "drop"].forEach(eventName => {
      dropArea.addEventListener(eventName, () => dropArea.classList.remove("drag"), false);
    });
    dropArea.addEventListener("drop", handleDrop, false);
    dropArea.addEventListener("click", () => fileInput.click());
  }
  fileInput?.addEventListener("change", handleFileSelect);

  $("#btnCamera")?.addEventListener("click", openCamera);
  $("#btnIdentify")?.addEventListener("click", processImageWithAI);
  $("#reprocessButton")?.addEventListener("click", processImageWithAI);
  $("#productForm")?.addEventListener("submit", saveProduct);
  $("#btnSaveSettings")?.addEventListener("click", saveSettings);
  $("#btnRemoveImage")?.addEventListener("click", removeImage);
}

function preventDefaults(e) {
  e.preventDefault();
  e.stopPropagation();
}

function handleDrop(e) {
  const files = e.dataTransfer.files;
  if (files.length > 0) handleFiles(files);
}

function handleFileSelect(e) {
  handleFiles(e.target.files);
}

function handleFiles(files) {
  if (files.length > 0 && files[0].type.startsWith("image/")) {
    setImage(files[0]);
  } else {
    log("Por favor, selecione um arquivo de imagem válido.", "error");
    updateAIStatus("Selecione uma imagem válida", "error");
  }
}

function setImage(file) {
  state.lastImageFile = file;
  $("#btnIdentify").disabled = false;
  $("#btnRemoveImage").style.display = "inline-flex";
  $("#uploadStatus").textContent = "Imagem carregada. Clique em 'Identificar com IA'";

  const reader = new FileReader();
  reader.onload = (e) => {
    $("#imagePreview").src = e.target.result;
    $("#imagePreview").style.display = "block";
    updateAIStatus("Pronto para análise", "info");
  };
  reader.readAsDataURL(file);
}

function openCamera() {
  log("Abrindo câmera...", "info");
  alert("Funcionalidade de câmera será implementada em breve.");
}

// ===== Processamento com IA =====
async function processImageWithAI() {
  if (!state.lastImageFile) {
    log("Selecione uma imagem primeiro.", "warning");
    updateAIStatus("Selecione uma imagem primeiro", "warning");
    return;
  }

  updateAIStatus("Analisando imagem...", "processing");
  const identifyButton = $("#btnIdentify");
  identifyButton.disabled = true;
  identifyButton.innerHTML = '<div class="spinner"></div> Processando...';

  try {
    const formData = new FormData();
    formData.append("image", state.lastImageFile);
    formData.append("uf", "SC");
    formData.append("regime", "SN");

    const response = await fetch(`${state.baseUrl}/vision/identify`, {
      method: "POST",
      body: formData
    });

    const result = await response.json();
    if (!response.ok) {
      // ALTERAÇÃO: Tenta pegar a mensagem de erro da API
      const errorDetail = result.detail || `HTTP ${response.status}: ${response.statusText}`;
      throw new Error(errorDetail);
    }

    state.lastAI = result;

    updateAIStatus(`Análise concluída (${Math.round(result.confidence * 100)}% confiança)`, "success");
    fillFormWithAIResults(result);
    $("#reprocessButton").disabled = false;
    log(`Produto identificado: ${result.title || "Desconhecido"}`, "success");

  } catch (error) {
    updateAIStatus("Falha na análise", "error");
    log(`Erro na identificação: ${error.message}`, "error");
    alert(`Ocorreu um erro na análise: ${error.message}`);
  } finally {
    // Garante que o botão seja restaurado
    identifyButton.disabled = false;
    identifyButton.innerHTML = '<i class="fas fa-robot"></i> Identificar com IA';
  }
}

function updateAIStatus(message, status) {
  const statusEl = $("#aiStatus");
  if (!statusEl) return;
  statusEl.innerHTML = `<i class="fas fa-${getStatusIcon(status)}"></i> ${message}`;
  statusEl.className = `chip ${status}`;
}

function getStatusIcon(status) {
  const icons = { processing: "spinner fa-spin", success: "check-circle", error: "exclamation-circle", warning: "exclamation-triangle", info: "info-circle" };
  return icons[status] || "info-circle";
}

function fillFormWithAIResults(result) {
  $("#productName").value = result.title || "";
  $("#productBrand").value = result.brand || "";
  $("#productGTIN").value = result.gtin || "";
  $("#productCategory").value = result.category || "";
  $("#productPrice").focus();
}

function removeImage() {
  resetIdentifyUI();
  log("Imagem removida", "info");
}

// ALTERAÇÃO: Função centralizada para limpar a UI de identificação
function resetIdentifyUI() {
  state.lastImageFile = null;
  state.lastAI = null;

  $("#imagePreview").style.display = "none";
  $("#imagePreview").src = "";
  $("#dropArea").style.display = "flex";

  $("#btnIdentify").disabled = true;
  $("#btnRemoveImage").style.display = "none";
  $("#uploadStatus").textContent = "Aguardando imagem...";

  $("#productForm").reset();
  updateAIStatus("Aguardando análise", "info");
}


// ===== Gerenciamento de Produtos =====
async function saveProduct(e) {
  e.preventDefault();

  const product = {
    title: $("#productName").value,
    brand: $("#productBrand").value,
    gtin: $("#productGTIN").value,
    category: $("#productCategory").value,
    price: parseFloat($("#productPrice").value),
    ncm: state.lastAI?.ncm || null,
    cest: state.lastAI?.cest || null,
    confidence: state.lastAI?.confidence || null
  };

  if (!product.title) {
    alert("O título do produto é obrigatório.");
    return;
  }

  try {
    const response = await fetch(`${state.baseUrl}/products/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(product)
    });

    const result = await response.json();
    if (!response.ok) {
      const errorDetail = result.detail || `HTTP ${response.status}`;
      throw new Error(errorDetail);
    }

    log(`Produto salvo: ${product.title} (ID: ${result.id})`, "success");
    alert("Produto salvo com sucesso!");

    // Recarrega os produtos da API para ter a lista mais recente
    await loadProducts();

    // Limpa a UI
    resetIdentifyUI();

    // Navega para a lista de produtos
    showPage('products');

  } catch (error) {
    log(`Erro ao salvar produto: ${error.message}`, "error");
    alert(`Erro ao salvar produto: ${error.message}`);
  }
}

function renderProducts() {
  const productsContainer = $("#productsContainer");
  if (!productsContainer) return;

  if (state.products.length === 0) {
    productsContainer.innerHTML = `<div class="card"><p class="muted">Nenhum produto cadastrado ainda.</p></div>`;
    return;
  }

  productsContainer.innerHTML = state.products.map(product => `
        <div class="card fade-in">
            <h3>${product.title}</h3>
            <p><strong>Marca:</strong> ${product.brand || "Não informada"}</p>
            <p><strong>Preço:</strong> R$ ${product.price ? product.price.toFixed(2).replace('.', ',') : "0,00"}</p>
            <p><strong>Categoria:</strong> ${product.category || "Não definida"}</p>
            ${product.gtin ? `<p><strong>GTIN:</strong> ${product.gtin}</p>` : ''}
            ${product.confidence ? `<p><strong>Confiança da IA:</strong> ${Math.round(product.confidence * 100)}%</p>` : ''}
            <small class="muted">Cadastrado em: ${new Date(product.created_at || new Date()).toLocaleString()}</small>
        </div>
    `).join('');
}

async function loadProducts() {
  try {
    const response = await fetch(`${state.baseUrl}/products`);
    if (response.ok) {
      const products = await response.json();
      state.products = products;
      log(`Carregados ${products.length} produtos da API`, "success");
    } else {
      log("Não foi possível carregar produtos da API, usando cache local", "warning");
    }
  } catch (error) {
    log(`Erro ao carregar produtos: ${error.message}`, "error");
  }
  updateStats();
}

// ===== Configurações =====
function saveSettings() {
  const apiUrl = $("#apiUrl").value;
  if (apiUrl) {
    state.baseUrl = apiUrl;
    localStorage.setItem("apiUrl", apiUrl);
    log(`URL da API atualizada para: ${apiUrl}`, "success");
    alert("Configurações salvas com sucesso!");
  } else {
    log("URL da API não pode estar vazia", "error");
    alert("Por favor, informe uma URL válida para a API.");
  }
}

// ===== Teste de Conexão =====
async function testConnection() {
  const statusEl = $("#connectionStatus");
  if (!statusEl) return;

  try {
    const response = await fetch(`${state.baseUrl}/test`);
    const data = await response.json();
    if (response.ok) {
      log(`Conexão bem-sucedida: ${data.message}`, "success");
      statusEl.textContent = "Conectado";
      statusEl.style.color = "var(--primary)";
    } else {
      throw new Error(data.detail || `HTTP ${response.status}`);
    }
  } catch (error) {
    log(`Falha na conexão: ${error.message}`, "error");
    statusEl.textContent = "Desconectado";
    statusEl.style.color = "#dc3545";
  }
}