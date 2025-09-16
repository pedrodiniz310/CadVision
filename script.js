// ===== Estado global =====
const state = {
  baseUrl: localStorage.getItem("apiUrl") || "http://localhost:8000",
  products: JSON.parse(localStorage.getItem("products") || "[]"),
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
  loadProducts();
  setupEventListeners();
  updateStats();
});

function initApp() {
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

  // Contar identificações por IA
  const aiCount = state.products.filter(p => p.identifiedByAI).length;
  if ($("#totalAI")) {
    $("#totalAI").textContent = aiCount;
  }
}

// ===== Upload e Processamento de Imagem =====
function setupEventListeners() {
  const dropArea = $("#dropArea");
  const fileInput = $("#fileInput");

  // Drag and drop
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
  fileInput.addEventListener("change", handleFileSelect);

  // Botão da câmera
  $("#btnCamera")?.addEventListener("click", openCamera);

  // Botões de processamento
  $("#btnIdentify")?.addEventListener("click", processImageWithAI);
  $("#reprocessButton")?.addEventListener("click", reprocessImage);
  $("#productForm")?.addEventListener("submit", saveProduct);

  // Configurações
  $("#btnSaveSettings")?.addEventListener("click", saveSettings);
  // Botão de remover imagem
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

function handleFileSelect() {
  handleFiles(this.files);
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
  $("#btnRemoveImage").style.display = "inline-flex"; // MOSTRAR BOTÃO
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
  // Em um cenário real, isso usaria a API MediaDevices.getUserMedia()
}

// ===== Processamento com IA =====
async function processImageWithAI() {
  if (!state.lastImageFile) {
    log("Selecione uma imagem primeiro.", "warning");
    updateAIStatus("Selecione uma imagem primeiro", "warning");
    return;
  }

  updateAIStatus("Analisando imagem...", "processing");
  $("#btnIdentify").disabled = true;
  $("#btnIdentify").innerHTML = '<div class="spinner"></div> Processando...';

  try {
    const formData = new FormData();
    formData.append("image", state.lastImageFile);
    formData.append("uf", "SC");
    formData.append("regime", "SN");

    const response = await fetch(`${state.baseUrl}/vision/identify`, {
      method: "POST",
      body: formData
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);

    const result = await response.json();
    state.lastAI = result;

    updateAIStatus(`Análise concluída (${Math.round(result.confidence * 100)}% confiança)`, "success");
    fillFormWithAIResults(result);
    $("#reprocessButton").disabled = false;
    $("#btnIdentify").disabled = false;
    $("#btnIdentify").innerHTML = '<i class="fas fa-robot"></i> Identificar com IA';

    log(`Produto identificado: ${result.title || "Desconhecido"}`, "success");
  } catch (error) {
    updateAIStatus("Falha na análise", "error");
    $("#btnIdentify").disabled = false;
    $("#btnIdentify").innerHTML = '<i class="fas fa-robot"></i> Identificar com IA';
    log(`Erro na identificação: ${error.message}`, "error");
  }
}

function updateAIStatus(message, status) {
  const statusEl = $("#aiStatus");
  if (!statusEl) return;

  statusEl.innerHTML = `<i class="fas fa-${getStatusIcon(status)}"></i> ${message}`;
  statusEl.style.background = getStatusColor(status);
}

function getStatusIcon(status) {
  const icons = {
    processing: "spinner fa-spin",
    success: "check-circle",
    error: "exclamation-circle",
    warning: "exclamation-triangle",
    info: "info-circle"
  };
  return icons[status] || "info-circle";
}

function getStatusColor(status) {
  const colors = {
    processing: "var(--muted)",
    success: "var(--primary)",
    error: "#dc3545",
    warning: "orange",
    info: "var(--accent)"
  };
  return colors[status] || "var(--chip)";
}

function fillFormWithAIResults(result) {
  if (result.title) $("#productName").value = result.title;
  if (result.brand) $("#productBrand").value = result.brand;
  if (result.gtin) $("#productGTIN").value = result.gtin;
  if (result.category) $("#productCategory").value = result.category;

  // Focar no preço para o usuário completar
  $("#productPrice").focus();
}

function reprocessImage() {
  if (state.lastImageFile) processImageWithAI();
}

function removeImage() {
  // Limpar estado
  state.lastImageFile = null;
  state.lastAI = null;

  // Limpar visualização
  $("#imagePreview").style.display = "none";
  $("#imagePreview").src = "";
  $("#dropArea").style.display = "flex";

  // Resetar botões
  $("#btnIdentify").disabled = true;
  $("#btnRemoveImage").style.display = "none";
  $("#uploadStatus").textContent = "Aguardando imagem...";

  // Limpar formulário
  $("#productForm").reset();
  updateAIStatus("Aguardando análise", "info");

  log("Imagem removida", "info");
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
    description: $("#productDescription").value,
    identifiedByAI: !!state.lastAI,
    confidence: state.lastAI?.confidence || 0,
    timestamp: new Date().toISOString()
  };

  try {
    // Salvar via API
    const response = await fetch(`${state.baseUrl}/products/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(product)
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const result = await response.json();

    // Salvar localmente
    product.id = result.id;
    state.products.unshift(product);
    localStorage.setItem("products", JSON.stringify(state.products));

    log(`Produto salvo: ${product.title} (ID: ${result.id})`, "success");
    alert("Produto salvo com sucesso!");

    // Limpar formulário
    $("#productForm").reset();
    $("#imagePreview").style.display = "none";
    $("#dropArea").style.display = "flex";
    state.lastImageFile = null;
    state.lastAI = null;
    updateAIStatus("Aguardando análise", "info");
    updateStats();
    // Limpar após salvar
    $("#productForm").reset();
    $("#imagePreview").style.display = "none";
    $("#dropArea").style.display = "flex";
    $("#btnRemoveImage").style.display = "none"; // ESCONDER BOTÃO
    state.lastImageFile = null;
    state.lastAI = null;
    updateAIStatus("Aguardando análise", "info");

  } catch (error) {
    log(`Erro ao salvar produto: ${error.message}`, "error");
    alert("Erro ao salvar produto. Verifique o console para detalhes.");
  }
}

function renderProducts() {
  const productsContainer = $("#productsContainer");
  if (!productsContainer) return;

  if (state.products.length === 0) {
    productsContainer.innerHTML = `
      <div class="card">
        <p class="muted">Nenhum produto cadastrado ainda.</p>
      </div>
    `;
    return;
  }

  productsContainer.innerHTML = state.products.map(product => `
    <div class="card fade-in">
      <h3>${product.title}</h3>
      <p><strong>Marca:</strong> ${product.brand || "Não informada"}</p>
      <p><strong>Preço:</strong> R$ ${product.price ? product.price.toFixed(2) : "0,00"}</p>
      <p><strong>Categoria:</strong> ${product.category || "Não definida"}</p>
      ${product.gtin ? `<p><strong>GTIN:</strong> ${product.gtin}</p>` : ''}
      ${product.confidence ? `<p><strong>Confiança da IA:</strong> ${Math.round(product.confidence * 100)}%</p>` : ''}
      <small class="muted">Cadastrado em: ${new Date(product.timestamp).toLocaleString()}</small>
    </div>
  `).join('');
}

async function loadProducts() {
  try {
    const response = await fetch(`${state.baseUrl}/products`);
    if (response.ok) {
      const products = await response.json();
      state.products = products;
      localStorage.setItem("products", JSON.stringify(products));
      log(`Carregados ${products.length} produtos da API`, "success");
    } else {
      log("Não foi possível carregar produtos da API, usando cache local", "warning");
    }
  } catch (error) {
    log(`Erro ao carregar produtos: ${error.message}`, "error");
  }
  updateStats();
  if (state.currentPage === "products") {
    renderProducts();
  }
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
  try {
    const response = await fetch(`${state.baseUrl}/test`);
    if (response.ok) {
      const data = await response.json();
      log(`Conexão bem-sucedida: ${data.message}`, "success");
      $("#connectionStatus").textContent = "Conectado";
      $("#connectionStatus").style.color = "green";
    } else {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (error) {
    log(`Falha na conexão: ${error.message}`, "error");
    $("#connectionStatus").textContent = "Desconectado";
    $("#connectionStatus").style.color = "red";
  }
}

// Adicionar teste de conexão na inicialização
document.addEventListener("DOMContentLoaded", () => {
  // Testar conexão após 2 segundos
  setTimeout(testConnection, 2000);
});