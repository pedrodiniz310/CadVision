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

/**
 * Exibe um modal de confirmação profissional em vez do confirm() padrão.
 * @param {string} title - O título do modal.
 * @param {string} message - A mensagem de confirmação.
 * @returns {Promise<boolean>} - Resolve como true se o usuário confirmar, false caso contrário.
 */
function showConfirmModal({ title, message, okText = "Confirmar", cancelText = "Cancelar", okClass = "btn-danger" }) {
  // Pega os elementos do modal do DOM
  const overlay = $('#confirmOverlay');
  const modal = $('#confirmModal');
  const titleEl = $('#confirmTitle');
  const messageEl = $('#confirmMessage');
  const okBtn = $('#confirmOk');
  const cancelBtn = $('#confirmCancel');

  // Preenche o conteúdo do modal
  titleEl.textContent = title;
  messageEl.innerHTML = message; // Usa innerHTML para permitir quebras de linha com <br>
  okBtn.textContent = okText;
  cancelBtn.textContent = cancelText;

  // Reseta e aplica a classe de estilo do botão OK
  okBtn.className = `btn ${okClass}`;

  // Mostra o modal com animação
  overlay.style.display = 'flex';
  setTimeout(() => overlay.classList.add('visible'), 10);

  return new Promise(resolve => {
    // Handler para os botões
    const handleOk = () => {
      closeModal();
      resolve(true);
    };

    const handleCancel = () => {
      closeModal();
      resolve(false);
    };

    // Função para fechar o modal e remover listeners
    const closeModal = () => {
      overlay.classList.remove('visible');
      // Espera a animação de fade-out terminar para esconder o overlay
      setTimeout(() => {
        overlay.style.display = 'none';
        okBtn.removeEventListener('click', handleOk);
        cancelBtn.removeEventListener('click', handleCancel);
        overlay.removeEventListener('click', handleOverlayClick);
      }, 300);
    };

    // Clicar fora do modal também fecha (cancela)
    const handleOverlayClick = (event) => {
      if (event.target === overlay) {
        handleCancel();
      }
    };

    // Adiciona os listeners de clique
    okBtn.addEventListener('click', handleOk);
    cancelBtn.addEventListener('click', handleCancel);
    overlay.addEventListener('click', handleOverlayClick);
  });
}

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
/**
 * Gerencia o estado de carregamento de um botão, mostrando um spinner.
 * @param {HTMLElement} button O elemento do botão a ser modificado.
 * @param {boolean} isLoading True para ativar o estado de carregamento, false para desativar.
 * @param {string} [loadingText='Identificando...'] O texto para exibir ao lado do spinner.
 */
function setButtonLoadingState(button, isLoading, loadingText = 'Identificando...') {
  if (!button) return;

  if (isLoading) {
    // Salva o conteúdo original do botão para poder restaurá-lo depois
    button.dataset.originalContent = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `
      <i class="fas fa-spinner fa-spin"></i>
      <span>${loadingText}</span>
    `;
  } else {
    // Restaura o conteúdo original que salvamos
    if (button.dataset.originalContent) {
      button.innerHTML = button.dataset.originalContent;
    }
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

  // --- ADIÇÕES PARA OS FILTROS ---
  DOM.filterCategory = $("#filterCategory");
  DOM.filterBrand = $("#filterBrand");
  DOM.filterSort = $("#filterSort");
  DOM.productsPagination = $("#productsPagination");
  DOM.paginationInfo = $("#paginationInfo");
  DOM.btnPrevPage = $("#btnPrevPage");
  DOM.btnNextPage = $("#btnNextPage");

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

  // --- LÓGICA PARA ATIVAR OS FILTROS DA PÁGINA DE PRODUTOS ---
  DOM.filterCategory?.addEventListener('change', () => loadProducts(1));
  DOM.filterBrand?.addEventListener('input', debounce(() => loadProducts(1), 500));
  DOM.filterSort?.addEventListener('change', () => loadProducts(1));

  // Configurações
  $("#btnSaveSettings")?.addEventListener("click", saveSettings);

  // Busca de produtos (se houver)
  const searchInput = $("#searchProducts");
  if (searchInput) {
    searchInput.addEventListener("input", debounce(searchProducts, CONFIG.DEBOUNCE_DELAY));
  }
  // --- LÓGICA DO NOVO DROPDOWN DE EXPORTAÇÃO ---
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

async function exportProducts(format = 'csv') {
  const exportButton = $('#btnExport'); // Usaremos o botão principal do dropdown
  if (!exportButton) return;

  // Usa a função de loading que já temos
  const originalContent = exportButton.innerHTML;
  setButtonLoadingState(exportButton, true, `Gerando .${format}...`);

  try {
    // 1. Pega os valores atuais dos filtros da tela
    const category = $('#filterCategory').value;
    const brand = $('#filterBrand').value;

    // 2. Constrói a URL com os parâmetros de filtro e formato
    const params = new URLSearchParams();
    if (category) params.append('category', category);
    if (brand) params.append('brand', brand);
    params.append('format', format);

    const url = `${CONFIG.BASE_URL}/products/export?${params.toString()}`;
    Logger.log(`Iniciando exportação para: ${url}`, "info");

    // 3. Faz a requisição e inicia o download
    const response = await fetch(url);
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || `Erro no servidor: ${response.statusText}`);
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
    showNotification(`Não foi possível gerar o relatório: ${error.message}`, "error");
  } finally {
    setButtonLoadingState(exportButton, false); // Desativa o loading
    exportButton.innerHTML = originalContent; // Restaura o conteúdo original do botão
  }
}

async function deleteProduct(productId, productTitle) {
  // Chama o novo modal e aguarda a resposta do usuário
  const confirmed = await showConfirmModal({
    title: "Confirmar Exclusão",
    message: `Você tem certeza que deseja excluir o produto <strong>"${productTitle}"</strong>?<br>Esta ação não pode ser desfeita.`,
    okText: "Sim, Excluir",
    okClass: "btn-danger" // Para deixar o botão de confirmação vermelho
  });

  // Se o usuário não confirmou (clicou em cancelar ou fora), para a execução
  if (!confirmed) {
    return;
  }

  try {
    const response = await fetch(`${CONFIG.BASE_URL}/products/${productId}`, {
      method: 'DELETE'
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.detail || result.message || 'Erro ao excluir');
    }

    Logger.log(`Produto ${productId} excluído com sucesso.`, "success");

    // --- INÍCIO DA CORREÇÃO ---
    // 1. Remove o produto da variável de estado local (STATE.products)
    STATE.products = STATE.products.filter(p => p.id !== productId);

    // 2. Remove a linha da tabela da interface
    const row = $(`#product-row-${productId}`);
    if (row) {
      row.remove();
    }

    // 3. Atualiza as estatísticas que dependem da contagem de produtos
    updateStats();
    // --- FIM DA CORREÇÃO ---

  } catch (error) {
    Logger.log(`Erro ao excluir produto: ${error.message}`, "error");
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

// Em frontend/js/script.js, substitua a função loadProducts

async function loadProducts(page = 1) {
  try {
    DOM.productsContainer.innerHTML = `<div class="card text-center muted">Carregando produtos...</div>`;

    // 1. Pega os valores atuais dos filtros E DA ORDENAÇÃO
    const category = DOM.filterCategory?.value || "";
    const brand = DOM.filterBrand?.value.trim() || "";
    const sort = DOM.filterSort?.value || "newest"; // <-- Já estava aqui, ótimo!

    // 2. Monta a URL com TODOS os parâmetros
    const params = new URLSearchParams({
      page: page,
      size: 10, // Define um tamanho de página
      sort: sort // <-- ADIÇÃO CRÍTICA AQUI
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
      </div>
    `;
    return;
  }

  // Constrói a estrutura da tabela com a nova coluna
  const tableHTML = `
    <div class="card p-0">
      <table class="table-products">
        <thead>
          <tr>
            <th>Produto</th>
            <th>Marca</th>
            <th>Categoria</th>  <th>GTIN/EAN</th>
            <th>NCM</th>
            <th>Cadastrado em</th>
            <th class="text-center">Ações</th>
          </tr>
        </thead>
        <tbody>
          ${STATE.products.map(product => `
            <tr id="product-row-${product.id}">
              <td class="product-title">
                ${escapeHtml(product.title)}
                ${product.confidence ? `<span class="badge badge-primary">${Math.round(product.confidence * 100)}%</span>` : ''}
              </td>
              <td>${escapeHtml(product.brand || 'N/A')}</td>
              <td>${escapeHtml(product.category || 'N/A')}</td> <td class="mono">${escapeHtml(product.gtin || 'N/A')}</td>
              <td class="mono">${escapeHtml(product.ncm || 'N/A')}</td>
              <td>${new Date(product.created_at).toLocaleDateString('pt-BR')}</td>
              <td class="actions">
                <button class="btn btn-secondary btn-sm" title="Editar">
                  <i class="fas fa-pencil-alt"></i>
                </button>
                <button class="btn btn-danger btn-sm" onclick="deleteProduct(${product.id}, '${escapeHtml(product.title)}')" title="Excluir">
                  <i class="fas fa-trash"></i>
                </button>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;

  DOM.productsContainer.innerHTML = tableHTML;
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