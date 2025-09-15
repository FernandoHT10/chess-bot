import os
import logging
import chess
import chess.engine
import chess.svg
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
import io
import cairosvg
import re

TOKEN = os.getenv("TELEGRAM_TOKEN")
STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "stockfish/stockfish-ubuntu-x86-64")

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Emojis para piezas y elementos del juego
EMOJIS = {
    'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗', 'N': '♘', 'P': '♙',
    'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟',
    'white_turn': '⚪',
    'black_turn': '⚫',
    'check': '⚠️',
    'mate': '♚⛔',
    'stalemate': '🤝',
    'evaluation': '📊',
    'warning': '⚠️',
    'success': '✅',
    'error': '❌',
    'undo': '↩️',
    'move': '♟️',
    'best_move': '🤖',
    'apply_best': '✅',
    'board': '🖼️',
    'fen': '📝',
    'position': '🎯',
    'reset': '🔄',
    'eval': '📈',
    'help': '❓',
    'menu': '📱'
}

# Estado del juego por chat
games = {}

# Teclados de botones
def get_main_keyboard():
    return ReplyKeyboardMarkup([
        [f"{EMOJIS['move']} Mover", f"{EMOJIS['best_move']} Mejor jugada"],
        [f"{EMOJIS['apply_best']} Aplicar mejor", f"{EMOJIS['board']} Tablero"],
        [f"{EMOJIS['undo']} Deshacer", f"{EMOJIS['reset']} Reiniciar"],
        [f"{EMOJIS['eval']} Evaluar", f"{EMOJIS['help']} Ayuda"]
    ], resize_keyboard=True, input_field_placeholder="Elige una opción...")

def get_move_keyboard():
    # Crear botones para las columnas (a-h)
    files = ["a", "b", "c", "d", "e", "f", "g", "h"]
    ranks = ["1", "2", "3", "4", "5", "6", "7", "8"]
    
    # Botones para selección de pieza (para notación SAN)
    piece_buttons = [
        [InlineKeyboardButton("K", callback_data="piece_K"),
        InlineKeyboardButton("Q", callback_data="piece_Q"),
        InlineKeyboardButton("R", callback_data="piece_R"),
        InlineKeyboardButton("B", callback_data="piece_B"),
        InlineKeyboardButton("N", callback_data="piece_N")]
    ]
    
    # Botones para filas y columnas
    file_buttons = []
    for i in range(0, 8, 4):
        file_buttons.append([InlineKeyboardButton(f, callback_data=f"file_{f}") for f in files[i:i+4]])
    
    rank_buttons = []
    for i in range(0, 8, 4):
        rank_buttons.append([InlineKeyboardButton(r, callback_data=f"rank_{r}") for r in ranks[i:i+4]])
    
    # Botón para cancelar
    cancel_button = [[InlineKeyboardButton("❌ Cancelar", callback_data="cancel_move")]]
    
    return InlineKeyboardMarkup(piece_buttons + file_buttons + rank_buttons + cancel_button)

class ChessGame:
    def __init__(self):
        self.board = chess.Board()
        self.history = []
        self.pending_move = {"from_sq": None, "to_sq": None, "promotion": None}
    
    def make_move(self, move):
        """Realiza un movimiento y guarda en historial"""
        self.history.append(self.board.fen())
        self.board.push(move)
        self.pending_move = {"from_sq": None, "to_sq": None, "promotion": None}
    
    def undo_move(self, num_moves=1):
        """Deshace el último movimiento o varios movimientos"""
        moves_undone = 0
        for _ in range(min(num_moves, len(self.history))):
            self.board = chess.Board(self.history.pop())
            moves_undone += 1
        return moves_undone

def generate_board_image(board):
    """Genera una imagen del tablero y la devuelve como bytes"""
    # Crear SVG del tablero
    svg = chess.svg.board(
        board=board,
        size=400,
        coordinates=True,
        lastmove=board.move_stack[-1] if board.move_stack else None
    )
    
    # Convertir SVG a PNG
    png_data = cairosvg.svg2png(bytestring=svg.encode('utf-8'))
    
    return png_data

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start con mensaje de bienvenida"""
    welcome_message = (
        f"{EMOJIS['K']} ¡Bienvenido al Bot de Ajedrez con Stockfish! {EMOJIS['k']}\n\n"
        "Puedes usar los botones para interactuar fácilmente o los comandos tradicionales:\n\n"
        "• /move <jugada> - Aplica una jugada (ej: e2e4 o Nf3)\n"
        "• /best [time] - Sugiere mejor jugada (tiempo opcional)\n"
        "• /applybest [time] - Aplica la mejor jugada\n"
        "• /board - Muestra el tablero actual como imagen\n"
        "• /fen - Muestra la posición en formato FEN\n"
        "• /position <FEN> - Establece una posición personalizada\n"
        "• /undo [n] - Deshace el último movimiento o n movimientos\n"
        "• /reset - Reinicia la partida\n"
        "• /eval [depth] - Evalúa la posición (profundidad opcional)\n\n"
        f"{EMOJIS['warning']} Usa notación UCI (e2e4) o SAN (Nf3)"
    )
    
    await update.message.reply_text(welcome_message, reply_markup=get_main_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la ayuda con los comandos disponibles"""
    help_text = (
        f"{EMOJIS['help']} <b>Comandos disponibles:</b>\n\n"
        f"{EMOJIS['move']} <b>Mover:</b> Realiza un movimiento en el tablero\n"
        f"{EMOJIS['best_move']} <b>Mejor jugada:</b> Sugiere la mejor jugada con Stockfish\n"
        f"{EMOJIS['apply_best']} <b>Aplicar mejor:</b> Aplica la mejor jugada sugerida\n"
        f"{EMOJIS['board']} <b>Tablero:</b> Muestra el tablero actual\n"
        f"{EMOJIS['undo']} <b>Deshacer:</b> Deshace el último movimiento\n"
        f"{EMOJIS['reset']} <b>Reiniciar:</b> Reinicia la partida\n"
        f"{EMOJIS['eval']} <b>Evaluar:</b> Evalúa la posición actual\n\n"
        "<b>Comandos de texto:</b>\n"
        "• /move <jugada> - Aplica una jugada (ej: e2e4 o Nf3)\n"
        "• /best [time] - Sugiere mejor jugada (tiempo opcional)\n"
        "• /applybest [time] - Aplica la mejor jugada\n"
        "• /board - Muestra el tablero actual\n"
        "• /fen - Muestra la posición en formato FEN\n"
        "• /position <FEN> - Establece una posición personalizada\n"
        "• /undo [n] - Deshace movimientos\n"
        "• /reset - Reinicia la partida\n"
        "• /eval [depth] - Evalúa la posición\n\n"
        f"{EMOJIS['warning']} Usa notación UCI (e2e4) o SAN (Nf3)"
    )
    
    await update.message.reply_text(help_text, parse_mode='HTML', reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las pulsaciones de los botones del teclado principal"""
    query = update.callback_query
    if query:
        await query.answer()
        message = query.message
        text = query.data
    else:
        message = update.message
        text = update.message.text
    
    chat_id = message.chat.id
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    
    # Determinar qué botón se pulsó
    if f"{EMOJIS['move']} Mover" in text or text == "move":
        await prompt_for_move(message, game)
    elif f"{EMOJIS['best_move']} Mejor jugada" in text or text == "best":
        await best_move(update, context, from_button=True)
    elif f"{EMOJIS['apply_best']} Aplicar mejor" in text or text == "applybest":
        await apply_best_move(update, context, from_button=True)
    elif f"{EMOJIS['board']} Tablero" in text or text == "board":
        await chess_board(update, context, from_button=True)
    elif f"{EMOJIS['undo']} Deshacer" in text or text == "undo":
        await undo_move(update, context, from_button=True)
    elif f"{EMOJIS['reset']} Reiniciar" in text or text == "reset":
        await reset_game(update, context, from_button=True)
    elif f"{EMOJIS['eval']} Evaluar" in text or text == "eval":
        await evaluate_position(update, context, from_button=True)
    elif f"{EMOJIS['help']} Ayuda" in text or text == "help":
        await help_command(update, context)
    else:
        await message.reply_text("Opción no reconocida. Usa /help para ver las opciones disponibles.")

async def prompt_for_move(message, game):
    """Solicita al usuario que ingrese un movimiento"""
    if game.board.is_game_over():
        await message.reply_text(
            f"{EMOJIS['warning']} La partida ya terminó\n"
            "Usa /reset para comenzar una nueva"
        )
        return
    
    # Mostrar teclado para selección de movimiento
    move_keyboard = get_move_keyboard()
    
    status = f"Turno: {'Blancas' + EMOJIS['white_turn'] if game.board.turn else 'Negras' + EMOJIS['black_turn']}\n"
    if game.board.is_check():
        status += f"{EMOJIS['check']} ¡Jaque!\n"
    
    await message.reply_text(
        f"{EMOJIS['move']} <b>Ingresa un movimiento:</b>\n\n"
        f"{status}\n"
        "Puedes:\n"
        "• Escribir la jugada (ej: e2e4 o Nf3)\n"
        "• Usar los botones para ayudarte a formar la jugada\n"
        "• Cancelar con el botón correspondiente",
        parse_mode='HTML',
        reply_markup=move_keyboard
    )

async def move_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones de movimiento"""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat.id
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    data = query.data
    
    if data == "cancel_move":
        await query.message.edit_text("Movimiento cancelado.", reply_markup=None)
        return
    
    # Procesar la selección de pieza, archivo o rango
    if data.startswith("piece_"):
        piece = data.split("_")[1]
        await query.message.reply_text(f"Seleccionaste la pieza: {piece}. Ahora ingresa la casilla de destino.")
        # Aquí podrías almacenar la pieza seleccionada en el estado del juego
    elif data.startswith("file_"):
        file = data.split("_")[1]
        await query.message.reply_text(f"Seleccionaste la columna: {file}. Ahora ingresa la fila.")
        # Aquí podrías almacenar el archivo seleccionado en el estado del juego
    elif data.startswith("rank_"):
        rank = data.split("_")[1]
        await query.message.reply_text(f"Seleccionaste la fila: {rank}.")
        # Aquí podrías almacenar el rango seleccionado en el estado del juego
    
    # Nota: Para una implementación completa, necesitarías manejar el estado de la selección
    # y construir el movimiento paso a paso. Esto es un ejemplo simplificado.

async def process_move_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa la entrada de movimiento del usuario"""
    chat_id = update.message.chat.id
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    move_text = update.message.text.strip()
    
    if game.board.is_game_over():
        await update.message.reply_text(
            f"{EMOJIS['warning']} La partida ya terminó\n"
            "Usa /reset para comenzar una nueva"
        )
        return
    
    try:
        # Intentar interpretar como notación UCI o SAN
        try:
            move = chess.Move.from_uci(move_text)
        except ValueError:
            move = game.board.parse_san(move_text)
        
        # Validar movimiento legal
        if move not in game.board.legal_moves:
            await update.message.reply_text(
                f"{EMOJIS['error']} Movimiento ilegal\n"
                f"{EMOJIS['warning']} Usa /best para sugerencias válidas"
            )
            return
        
        # Realizar movimiento
        san_move = game.board.san(move)
        game.make_move(move)
        
        # Generar imagen del nuevo estado del tablero
        png_data = generate_board_image(game.board)
        
        with io.BytesIO(png_data) as photo:
            photo.name = 'tablero.png'
            await update.message.reply_photo(
                photo=photo,
                caption=(
                    f"{EMOJIS['success']} Movimiento aplicado:\n"
                    f"• SAN: {san_move}\n"
                    f"• UCI: {move.uci()}\n"
                    f"• Turno actual: {'Blancas' + EMOJIS['white_turn'] if game.board.turn else 'Negras' + EMOJIS['black_turn']}"
                ),
                reply_markup=get_main_keyboard()
            )
        
    except ValueError as e:
        await update.message.reply_text(
            f"{EMOJIS['error']} Movimiento inválido: {str(e)}\n"
            f"{EMOJIS['warning']} Usa notación UCI (e2e4) or SAN (Nf3) o los botones de ayuda"
        )

async def chess_board(update: Update, context: ContextTypes.DEFAULT_TYPE, from_button=False):
    """Muestra el tablero actual como imagen"""
    if hasattr(update, 'message'):
        chat_id = update.message.chat.id
    else:
        chat_id = update.callback_query.message.chat.id
        
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    
    try:
        # Generar imagen del tablero
        png_data = generate_board_image(game.board)
        
        # Información de turno y estado
        turn = "Blancas" + EMOJIS['white_turn'] if game.board.turn else "Negras" + EMOJIS['black_turn']
        status = f"Turno: {turn}\n"
        
        if game.board.is_check():
            status += f"{EMOJIS['check']} ¡Jaque!\n"
        if game.board.is_game_over():
            if game.board.is_checkmate():
                status += f"{EMOJIS['mate']} ¡Jaque mate!\n"
            elif game.board.is_stalemate():
                status += f"{EMOJIS['stalemate']} Tablas por ahogado\n"
        
        # Enviar imagen
        with io.BytesIO(png_data) as photo:
            photo.name = 'tablero.png'
            if from_button and hasattr(update, 'callback_query'):
                await update.callback_query.message.reply_photo(
                    photo=photo, 
                    caption=status,
                    reply_markup=get_main_keyboard()
                )
            else:
                await update.message.reply_photo(
                    photo=photo, 
                    caption=status,
                    reply_markup=get_main_keyboard()
                )
            
    except Exception as e:
        logger.error(f"Error generando imagen del tablero: {e}")
        # Fallback a representación textual si hay error con la imagen
        board_str = str(game.board).replace(' ', '').replace('\n', '')
        if from_button and hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text(
                f"{EMOJIS['error']} Error al generar imagen. Aquí está el tablero en texto:\n\n"
                f"`{board_str}`\n\n{status}",
                parse_mode='MarkdownV2',
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_text(
                f"{EMOJIS['error']} Error al generar imagen. Aquí está el tablero en texto:\n\n"
                f"`{board_str}`\n\n{status}",
                parse_mode='MarkdownV2',
                reply_markup=get_main_keyboard()
            )

def format_evaluation(score):
    """Formatea la evaluación con emojis - Versión compatible con PovScore"""
    # Obtener la evaluación desde la perspectiva de las blancas
    white_score = score.white()
    
    if white_score.is_mate():
        mate_in = white_score.mate()
        if mate_in > 0:
            return f"{EMOJIS['white_turn']} Mate en {mate_in}"
        else:
            return f"{EMOJIS['black_turn']} Mate en {abs(mate_in)}"
    else:
        # Para puntuaciones en centipawns
        cp = white_score.score()
        if cp is None:
            return "Posición igualada"
        
        # Ajustar la perspectiva según el turno
        if cp > 0:
            return f"{EMOJIS['white_turn']} +{cp/100:.2f}"
        elif cp < 0:
            return f"{EMOJIS['black_turn']} {cp/100:.2f}"
        else:
            return "Igualado"

async def best_move(update: Update, context: ContextTypes.DEFAULT_TYPE, from_button=False):
    """Sugiere la mejor jugada usando Stockfish"""
    if hasattr(update, 'message'):
        chat_id = update.message.chat.id
    else:
        chat_id = update.callback_query.message.chat.id
        
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    
    if game.board.is_game_over():
        if from_button and hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text(
                f"{EMOJIS['warning']} La partida ya terminó\n"
                "Usa /reset para comenzar una nueva",
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_text(
                f"{EMOJIS['warning']} La partida ya terminó\n"
                "Usa /reset para comenzar una nueva",
                reply_markup=get_main_keyboard()
            )
        return
    
    # Tiempo de análisis por defecto: 0.5 segundos
    analysis_time = 0.5
    if context.args:
        try:
            analysis_time = float(context.args[0])
        except ValueError:
            pass
    
    try:
        with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
            result = engine.analyse(
                game.board,
                chess.engine.Limit(time=analysis_time),
                multipv=1
            )
            
            if not result or 'pv' not in result[0]:
                if from_button and hasattr(update, 'callback_query'):
                    await update.callback_query.message.reply_text(
                        f"{EMOJIS['error']} No se pudo encontrar movimiento",
                        reply_markup=get_main_keyboard()
                    )
                else:
                    await update.message.reply_text(
                        f"{EMOJIS['error']} No se pudo encontrar movimiento",
                        reply_markup=get_main_keyboard()
                    )
                return
            
            best_move = result[0]['pv'][0]
            san_move = game.board.san(best_move)
            
            # Formatear evaluación
            score = result[0]['score']
            eval_str = format_evaluation(score)
            
            # Generar imagen con el movimiento sugerido resaltado
            board_copy = game.board.copy()
            board_copy.push(best_move)
            png_data = generate_board_image(board_copy)
            
            with io.BytesIO(png_data) as photo:
                photo.name = 'mejor_jugada.png'
                if from_button and hasattr(update, 'callback_query'):
                    await update.callback_query.message.reply_photo(
                        photo=photo,
                        caption=(
                            f"{EMOJIS['evaluation']} Mejor jugada:\n"
                            f"• SAN: {san_move}\n"
                            f"• UCI: {best_move.uci()}\n"
                            f"• Evaluación: {eval_str}\n"
                            f"• Tiempo análisis: {analysis_time}s\n\n"
                            f"{EMOJIS['warning']} Usa /applybest para aplicar esta jugada"
                        ),
                        reply_markup=get_main_keyboard()
                    )
                else:
                    await update.message.reply_photo(
                        photo=photo,
                        caption=(
                            f"{EMOJIS['evaluation']} Mejor jugada:\n"
                            f"• SAN: {san_move}\n"
                            f"• UCI: {best_move.uci()}\n"
                            f"• Evaluación: {eval_str}\n"
                            f"• Tiempo análisis: {analysis_time}s\n\n"
                            f"{EMOJIS['warning']} Usa /applybest para aplicar esta jugada"
                        ),
                        reply_markup=get_main_keyboard()
                    )
            
    except Exception as e:
        logger.error(f"Error con Stockfish: {e}")
        if from_button and hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text(
                f"{EMOJIS['error']} Error al analizar con Stockfish",
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_text(
                f"{EMOJIS['error']} Error al analizar con Stockfish",
                reply_markup=get_main_keyboard()
            )

async def apply_best_move(update: Update, context: ContextTypes.DEFAULT_TYPE, from_button=False):
    """Aplica la mejor jugada sugerida por Stockfish"""
    if hasattr(update, 'message'):
        chat_id = update.message.chat.id
    else:
        chat_id = update.callback_query.message.chat.id
        
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    
    if game.board.is_game_over():
        if from_button and hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text(
                f"{EMOJIS['warning']} La partida ya terminó\n"
                "Usa /reset para comenzar una nueva",
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_text(
                f"{EMOJIS['warning']} La partida ya terminó\n"
                "Usa /reset para comenzar una nueva",
                reply_markup=get_main_keyboard()
            )
        return
    
    analysis_time = 0.5
    if context.args:
        try:
            analysis_time = float(context.args[0])
        except ValueError:
            pass
    
    try:
        with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
            result = engine.analyse(
                game.board,
                chess.engine.Limit(time=analysis_time),
                multipv=1
            )
            
            if not result or 'pv' not in result[0]:
                if from_button and hasattr(update, 'callback_query'):
                    await update.callback_query.message.reply_text(
                        f"{EMOJIS['error']} No se pudo encontrar movimiento",
                        reply_markup=get_main_keyboard()
                    )
                else:
                    await update.message.reply_text(
                        f"{EMOJIS['error']} No se pudo encontrar movimiento",
                        reply_markup=get_main_keyboard()
                    )
                return
            
            best_move = result[0]['pv'][0]
            san_move = game.board.san(best_move)
            
            # Aplicar movimiento
            game.make_move(best_move)
            
            # Generar imagen del nuevo estado
            png_data = generate_board_image(game.board)
            
            # Obtener evaluación para el nuevo estado
            new_result = engine.analyse(
                game.board,
                chess.engine.Limit(time=0.1),
                multipv=1
            )
            new_eval = format_evaluation(new_result[0]['score'])
            
            with io.BytesIO(png_data) as photo:
                photo.name = 'tablero_actualizado.png'
                if from_button and hasattr(update, 'callback_query'):
                    await update.callback_query.message.reply_photo(
                        photo=photo,
                        caption=(
                            f"{EMOJIS['success']} Mejor jugada aplicada:\n"
                            f"• SAN: {san_move}\n"
                            f"• UCI: {best_move.uci()}\n"
                            f"• Nueva evaluación: {new_eval}\n"
                            f"• Turno actual: {'Blancas' + EMOJIS['white_turn'] if game.board.turn else 'Negras' + EMOJIS['black_turn']}"
                        ),
                        reply_markup=get_main_keyboard()
                    )
                else:
                    await update.message.reply_photo(
                        photo=photo,
                        caption=(
                            f"{EMOJIS['success']} Mejor jugada aplicada:\n"
                            f"• SAN: {san_move}\n"
                            f"• UCI: {best_move.uci()}\n"
                            f"• Nueva evaluación: {new_eval}\n"
                            f"• Turno actual: {'Blancas' + EMOJIS['white_turn'] if game.board.turn else 'Negras' + EMOJIS['black_turn']}"
                        ),
                        reply_markup=get_main_keyboard()
                    )
            
    except Exception as e:
        logger.error(f"Error aplicando mejor movimiento: {e}")
        if from_button and hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text(
                f"{EMOJIS['error']} Error al aplicar movimiento",
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_text(
                f"{EMOJIS['error']} Error al aplicar movimiento",
                reply_markup=get_main_keyboard()
            )

async def show_fen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la posición actual en formato FEN"""
    chat_id = update.message.chat.id
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    await update.message.reply_text(f"`{game.board.fen()}`", parse_mode='MarkdownV2', reply_markup=get_main_keyboard())

async def set_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Establece una posición personalizada mediante FEN"""
    chat_id = update.message.chat.id
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    
    if not context.args:
        await update.message.reply_text(
            f"{EMOJIS['error']} Debes proporcionar una posición FEN\n"
            "Ejemplo: /position rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            reply_markup=get_main_keyboard()
        )
        return
    
    fen = " ".join(context.args)
    try:
        game.board = chess.Board(fen)
        game.history = []
        
        # Generar imagen de la nueva posición
        png_data = generate_board_image(game.board)
        
        with io.BytesIO(png_data) as photo:
            photo.name = 'nueva_posicion.png'
            await update.message.reply_photo(
                photo=photo,
                caption=(
                    f"{EMOJIS['success']} Posición establecida correctamente\n"
                    f"Turno: {'Blancas' + EMOJIS['white_turn'] if game.board.turn else 'Negras' + EMOJIS['black_turn']}"
                ),
                reply_markup=get_main_keyboard()
            )
    except ValueError as e:
        await update.message.reply_text(
            f"{EMOJIS['error']} FEN inválido: {str(e)}",
            reply_markup=get_main_keyboard()
        )

async def undo_move(update: Update, context: ContextTypes.DEFAULT_TYPE, from_button=False):
    """Deshace el último movimiento o varios movimientos"""
    if hasattr(update, 'message'):
        chat_id = update.message.chat.id
    else:
        chat_id = update.callback_query.message.chat.id
        
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    
    if not game.history:
        if from_button and hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text(
                f"{EMOJIS['warning']} No hay movimientos para deshacer",
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_text(
                f"{EMOJIS['warning']} No hay movimientos para deshacer",
                reply_markup=get_main_keyboard()
            )
        return
    
    # Determinar cuántos movimientos deshacer
    num_moves = 1
    if context.args:
        try:
            num_moves = int(context.args[0])
            if num_moves < 1:
                await update.message.reply_text(
                    f"{EMOJIS['error']} Debe ser un número positivo",
                    reply_markup=get_main_keyboard()
                )
                return
        except ValueError:
            await update.message.reply_text(
                f"{EMOJIS['error']} Número inválido",
                reply_markup=get_main_keyboard()
            )
            return
    
    # Verificar que no se intenten deshacer más movimientos de los disponibles
    if num_moves > len(game.history):
        num_moves = len(game.history)
        if from_button and hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text(
                f"{EMOJIS['warning']} Solo hay {num_moves} movimientos en el historial. "
                f"Deshaciendo {num_moves} movimientos.",
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_text(
                f"{EMOJIS['warning']} Solo hay {num_moves} movimientos en el historial. "
                f"Deshaciendo {num_moves} movimientos.",
                reply_markup=get_main_keyboard()
            )
    
    # Deshacer movimientos
    moves_undone = game.undo_move(num_moves)
    
    # Generar imagen del tablero después de deshacer
    png_data = generate_board_image(game.board)
    
    with io.BytesIO(png_data) as photo:
        photo.name = 'tablero_deshacer.png'
        if from_button and hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_photo(
                photo=photo,
                caption=(
                    f"{EMOJIS['undo']} Deshecho(s) {moves_undone} movimiento(s)\n"
                    f"Turno: {'Blancas' + EMOJIS['white_turn'] if game.board.turn else 'Negras' + EMOJIS['black_turn']}\n"
                    f"Movimientos restantes en historial: {len(game.history)}"
                ),
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_photo(
                photo=photo,
                caption=(
                    f"{EMOJIS['undo']} Deshecho(s) {moves_undone} movimiento(s)\n"
                    f"Turno: {'Blancas' + EMOJIS['white_turn'] if game.board.turn else 'Negras' + EMOJIS['black_turn']}\n"
                    f"Movimientos restantes en historial: {len(game.history)}"
                ),
                reply_markup=get_main_keyboard()
            )

async def reset_game(update: Update, context: ContextTypes.DEFAULT_TYPE, from_button=False):
    """Reinicia la partida a la posición inicial"""
    if hasattr(update, 'message'):
        chat_id = update.message.chat.id
    else:
        chat_id = update.callback_query.message.chat.id
        
    games[chat_id] = ChessGame()
    
    # Generar imagen del tablero inicial
    game = games[chat_id]
    png_data = generate_board_image(game.board)
    
    with io.BytesIO(png_data) as photo:
        photo.name = 'tablero_inicial.png'
        if from_button and hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_photo(
                photo=photo,
                caption=(
                    f"{EMOJIS['success']} Partida reiniciada\n"
                    f"Turno: Blancas{EMOJIS['white_turn']}"
                ),
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_photo(
                photo=photo,
                caption=(
                    f"{EMOJIS['success']} Partida reiniciada\n"
                    f"Turno: Blancas{EMOJIS['white_turn']}"
                ),
                reply_markup=get_main_keyboard()
            )

async def evaluate_position(update: Update, context: ContextTypes.DEFAULT_TYPE, from_button=False):
    """Evalúa la posición actual con Stockfish"""
    if hasattr(update, 'message'):
        chat_id = update.message.chat.id
    else:
        chat_id = update.callback_query.message.chat.id
        
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    
    if game.board.is_game_over():
        if from_button and hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text(
                f"{EMOJIS['warning']} La partida ya terminó\n"
                "Usa /reset para comenzar una nueva",
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_text(
                f"{EMOJIS['warning']} La partida ya terminó\n"
                "Usa /reset para comenzar una nueva",
                reply_markup=get_main_keyboard()
            )
        return
    
    # Profundidad por defecto: 10
    depth = 10
    if context.args:
        try:
            depth = int(context.args[0])
        except ValueError:
            pass
    
    try:
        with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
            result = engine.analyse(
                game.board,
                chess.engine.Limit(depth=depth),
                multipv=1
            )
            
            if not result or 'score' not in result[0]:
                if from_button and hasattr(update, 'callback_query'):
                    await update.callback_query.message.reply_text(
                        f"{EMOJIS['error']} No se pudo evaluar la posición",
                        reply_markup=get_main_keyboard()
                    )
                else:
                    await update.message.reply_text(
                        f"{EMOJIS['error']} No se pudo evaluar la posición",
                        reply_markup=get_main_keyboard()
                    )
                return
            
            score = result[0]['score']
            eval_str = format_evaluation(score)
            
            # Información adicional
            pv_moves = [game.board.san(move) for move in result[0]['pv'][:5]]
            pv_str = " ".join(pv_moves)
            
            # Generar imagen del tablero actual
            png_data = generate_board_image(game.board)
            
            with io.BytesIO(png_data) as photo:
                photo.name = 'evaluacion.png'
                if from_button and hasattr(update, 'callback_query'):
                    await update.callback_query.message.reply_photo(
                        photo=photo,
                        caption=(
                            f"{EMOJIS['evaluation']} Evaluación de posición:\n"
                            f"• Resultado: {eval_str}\n"
                            f"• Profundidad: {depth}\n"
                            f"• Variación principal: {pv_str}\n"
                            f"• Turno: {'Blancas' + EMOJIS['white_turn'] if game.board.turn else 'Negras' + EMOJIS['black_turn']}"
                        ),
                        reply_markup=get_main_keyboard()
                    )
                else:
                    await update.message.reply_photo(
                        photo=photo,
                        caption=(
                            f"{EMOJIS['evaluation']} Evaluación de posición:\n"
                            f"• Resultado: {eval_str}\n"
                            f"• Profundidad: {depth}\n"
                            f"• Variación principal: {pv_str}\n"
                            f"• Turno: {'Blancas' + EMOJIS['white_turn'] if game.board.turn else 'Negras' + EMOJIS['black_turn']}"
                        ),
                        reply_markup=get_main_keyboard()
                    )
            
    except Exception as e:
        logger.error(f"Error en evaluación: {e}")
        if from_button and hasattr(update, 'callback_query'):
            await update.callback_query.message.reply_text(
                f"{EMOJIS['error']} Error al evaluar posición",
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_text(
                f"{EMOJIS['error']} Error al evaluar posición",
                reply_markup=get_main_keyboard()
            )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja errores no capturados"""
    logger.error(f"Error: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            f"{EMOJIS['error']} Error interno del bot\n"
            "Por favor, intenta nuevamente",
            reply_markup=get_main_keyboard()
        )

def main():
    """Inicia el bot"""
    application = Application.builder().token(TOKEN).build()
    
    # Handlers de comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("move", make_move))
    application.add_handler(CommandHandler("best", best_move))
    application.add_handler(CommandHandler("applybest", apply_best_move))
    application.add_handler(CommandHandler("board", chess_board))
    application.add_handler(CommandHandler("fen", show_fen))
    application.add_handler(CommandHandler("position", set_position))
    application.add_handler(CommandHandler("undo", undo_move))
    application.add_handler(CommandHandler("reset", reset_game))
    application.add_handler(CommandHandler("eval", evaluate_position))
    application.add_handler(CommandHandler("help", help_command))
    
    # Handler para mensajes de texto (movimientos)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_move_input))
    
    # Handler para botones del teclado principal
    application.add_handler(MessageHandler(filters.TEXT & (
        filters.Regex(f"^{re.escape(EMOJIS['move'])} Mover$") |
        filters.Regex(f"^{re.escape(EMOJIS['best_move'])} Mejor jugada$") |
        filters.Regex(f"^{re.escape(EMOJIS['apply_best'])} Aplicar mejor$") |
        filters.Regex(f"^{re.escape(EMOJIS['board'])} Tablero$") |
        filters.Regex(f"^{re.escape(EMOJIS['undo'])} Deshacer$") |
        filters.Regex(f"^{re.escape(EMOJIS['reset'])} Reiniciar$") |
        filters.Regex(f"^{re.escape(EMOJIS['eval'])} Evaluar$") |
        filters.Regex(f"^{re.escape(EMOJIS['help'])} Ayuda$")
    ), button_handler))
    
    # Handler para botones inline (movimientos)
    application.add_handler(CallbackQueryHandler(move_button_handler, pattern="^(piece_|file_|rank_|cancel_move)"))
    
    # Manejo de errores
    application.add_error_handler(error_handler)
    
    # Iniciar bot
    application.run_polling()
    logger.info("Bot iniciado correctamente")

if __name__ == "__main__":
    main()