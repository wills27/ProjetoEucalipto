import re


def clean_training_log_line(line):
    message = line.strip()
    match = re.match(r"^\d{4}-\d{2}-\d{2}[^]]+\]\s*(.*)$", message)
    if match:
        return match.group(1).strip()
    return message


def parse_training_log_line(line, friendly_error_callback=None):
    message = clean_training_log_line(line)

    loss_match = re.search(
        r"\b(\d+),\s+train_loss=([^\s,]+),\s+test_loss=([^\s,]+),\s+LR=([^\s,]+),\s+time\s+([0-9.]+)s",
        message,
    )
    if loss_match:
        epoch_index = int(loss_match.group(1))
        return {
            "type": "epoch",
            "epoch": epoch_index + 1,
            "plot_epoch": epoch_index,
            "train_loss": loss_match.group(2),
            "val_loss": loss_match.group(3),
            "lr": loss_match.group(4),
            "cellpose_time": loss_match.group(5),
        }

    if "%|" in message and "100%" in message:
        return {"type": "internal_progress"}

    normalized = message.lower()
    if "etapa:" in normalized:
        if "carregando dados de treino" in normalized:
            return {"type": "stage", "key": "dados_treino", "title": "Carregando dados de treino"}
        if "carregando dados de validacao" in normalized:
            return {"type": "stage", "key": "dados_validacao", "title": "Carregando dados de validacao"}
        if "inicializando modelo" in normalized:
            return {"type": "stage", "key": "inicializar_modelo", "title": "Inicializando modelo"}
        if "treinamento principal iniciado" in normalized:
            return {"type": "stage", "key": "treinar", "title": "Treinando rede"}
        if "treinamento finalizado" in normalized:
            return {"type": "stage", "key": "concluido", "title": "Treinamento finalizado"}

    train_count_match = re.search(r"imagens de treino:\s*(\d+)", normalized)
    if train_count_match:
        return {"type": "dataset_count", "kind": "train", "count": int(train_count_match.group(1))}
    val_count_match = re.search(r"imagens de validacao:\s*(\d+)", normalized)
    if val_count_match:
        return {"type": "dataset_count", "kind": "val", "count": int(val_count_match.group(1))}
    if "usando gpu:" in normalized:
        gpu_state = message.split(":", 1)[-1].strip()
        return {"type": "detail", "text": f"GPU detectada: {gpu_state}"}
    if "saving network parameters" in normalized:
        return {"type": "detail", "text": "Checkpoint interno do modelo salvo"}
    if "modelo salvo em:" in normalized:
        return {"type": "model_saved", "path": message.split(":", 1)[-1].strip()}
    if "limpando arquivos temporarios" in normalized:
        return {"type": "detail", "text": "Limpando arquivos temporarios do treino"}
    if "training flows apagados:" in normalized:
        return {"type": "detail", "text": "Arquivos temporarios do treino removidos"}
    if any(marker in message for marker in ["Traceback", "RuntimeError", "Exception", "CUDA out of memory"]):
        text = friendly_error_callback(message) if friendly_error_callback else message
        return {"type": "error", "text": text}
    return None
