import logging
import chess
import chess.engine
import chess.svg
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import io
import cairosvg
import os

# Configuración inicial

TOKEN = os.getenv("TELEGRAM_TOKEN")
STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "stockfish/stockfish-ubuntu-x86-64")

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Emojis mejorados para piezas y elementos del juego
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
    'reset': '🔄',
    'move': '↪️',
    'best_move': '⭐',
    'apply_move': '🚀',
    'board': '🎯',
    'fen': '📝',
    'position': '🎮',
    'eval': '🧠',
    'category': '📂',
    'common_moves': '🎯'
}

# Estado del juego por chat
games = {}

# Constantes para callback data
MAIN_MENU, BOARD_MENU, MOVE_MENU, EVAL_MENU = range(4)
COMMON_MOVES = {
    "e2e4": "e2e4",
    "d2d4": "d2d4", 
    "Nf3": "Nf3",
    "Nc3": "Nc3",
    "g2g3": "g2g3",
    "c2c4": "c2c4"
}

class ChessGame:
    def __init__(self):
        self.board = chess.Board()
        self.history = []
    
    def make_move(self, move):
        """Realiza un movimiento y guarda en historial"""
        self.history.append(self.board.fen())
        self.board.push(move)
    
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
    """Maneja el comando /start con mensaje de bienvenida y menú principal"""
    welcome_message = (
        f"{EMOJIS['K']} ¡Bienvenido al Bot de Ajedrez con Stockfish! {EMOJIS['k']}\n\n"
        "💡 *Características principales:*\n"
        "• Motor Stockfish integrado\n"
        "• Visualización de tablero\n"
        "• Análisis de posiciones\n"
        "• Sugerencias de jugadas\n"
        "• Movimientos rápidos con botones\n\n"
        f"{EMOJIS['warning']} Usa notación UCI (e2e4) o SAN (Nf3)"
    )
    
    # Crear teclado inline con menú principal
    keyboard = [
        [InlineKeyboardButton(f"{EMOJIS['board']} Tablero", callback_data="board_menu")],
        [InlineKeyboardButton(f"{EMOJIS['move']} Movimientos", callback_data="move_menu")],
        [InlineKeyboardButton(f"{EMOJIS['eval']} Evaluación", callback_data="eval_menu")],
        [InlineKeyboardButton(f"{EMOJIS['common_moves']} Jugadas Rápidas", callback_data="common_moves")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_message, 
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def handle_menu_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las selecciones del menú inline"""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    
    # Determinar qué menú mostrar según la selección
    if query.data == "board_menu":
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['board']} Mostrar Tablero", callback_data="show_board")],
            [InlineKeyboardButton(f"{EMOJIS['fen']} Mostrar FEN", callback_data="show_fen")],
            [InlineKeyboardButton(f"{EMOJIS['position']} Establecer Posición", callback_data="set_position")],
            [InlineKeyboardButton(f"{EMOJIS['undo']} Volver al Menú Principal", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"{EMOJIS['category']} *Menú de Tablero*\n\n"
            "Selecciona una opción:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    elif query.data == "move_menu":
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['move']} Hacer Movimiento", callback_data="make_move_menu")],
            [InlineKeyboardButton(f"{EMOJIS['best_move']} Mejor Jugada", callback_data="best_move_menu")],
            [InlineKeyboardButton(f"{EMOJIS['apply_move']} Aplicar Mejor Jugada", callback_data="apply_best_menu")],
            [InlineKeyboardButton(f"{EMOJIS['undo']} Deshacer Movimiento", callback_data="undo_move_menu")],
            [InlineKeyboardButton(f"{EMOJIS['undo']} Volver al Menú Principal", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"{EMOJIS['category']} *Menú de Movimientos*\n\n"
            "Selecciona una opción:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    elif query.data == "eval_menu":
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['eval']} Evaluar Posición", callback_data="evaluate_position")],
            [InlineKeyboardButton(f"{EMOJIS['undo']} Volver al Menú Principal", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"{EMOJIS['category']} *Menú de Evaluación*\n\n"
            "Selecciona una opción:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    elif query.data == "common_moves":
        # Crear botones para jugadas rápidas
        keyboard = []
        row = []
        for i, (name, move) in enumerate(COMMON_MOVES.items()):
            row.append(InlineKeyboardButton(name, callback_data=f"quick_move_{move}"))
            if (i + 1) % 2 == 0:  # Dos botones por fila
                keyboard.append(row)
                row = []
        if row:  # Añadir la última fila si no está completa
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton(f"{EMOJIS['undo']} Volver", callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"{EMOJIS['common_moves']} *Jugadas Rápidas*\n\n"
            "Selecciona un movimiento:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    elif query.data == "main_menu":
        # Volver al menú principal
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['board']} Tablero", callback_data="board_menu")],
            [InlineKeyboardButton(f"{EMOJIS['move']} Movimientos", callback_data="move_menu")],
            [InlineKeyboardButton(f"{EMOJIS['eval']} Evaluación", callback_data="eval_menu")],
            [InlineKeyboardButton(f"{EMOJIS['common_moves']} Jugadas Rápidas", callback_data="common_moves")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"{EMOJIS['category']} *Menú Principal*\n\n"
            "Selecciona una categoría:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    # Manejar otras opciones de menú
    elif query.data == "show_board":
        await show_board_callback(update, context)
    elif query.data == "show_fen":
        await show_fen_callback(update, context)
    elif query.data.startswith("quick_move_"):
        move_uci = query.data.replace("quick_move_", "")
        context.args = [move_uci]
        await make_move_callback(update, context)

async def show_board_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la solicitud de mostrar tablero desde el menú"""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    
    try:
        # Generar imagen del tablero
        png_data = generate_board_image(game.board)
        
        # Información de turno y estado
        status = get_board_status(game.board)
        
        # Botones adicionales
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['undo']} Deshacer", callback_data="undo_move_menu"),
             InlineKeyboardButton(f"{EMOJIS['reset']} Reiniciar", callback_data="reset_game")],
            [InlineKeyboardButton(f"{EMOJIS['best_move']} Mejor Jugada", callback_data="best_move_menu")],
            [InlineKeyboardButton(f"{EMOJIS['undo']} Volver al Menú", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Enviar imagen
        with io.BytesIO(png_data) as photo:
            photo.name = 'tablero.png'
            await query.message.reply_photo(
                photo=photo, 
                caption=status,
                reply_markup=reply_markup
            )
            
    except Exception as e:
        logger.error(f"Error generando imagen del tablero: {e}")
        await query.message.reply_text(
            f"{EMOJIS['error']} Error al generar imagen del tablero"
        )

def get_board_status(board):
    """Obtiene el estado del tablero con formato mejorado"""
    turn = "Blancas" + EMOJIS['white_turn'] if board.turn else "Negras" + EMOJIS['black_turn']
    status = f"♟️ *Tablero Actual* ♟️\n\n"
    status += f"• Turno: {turn}\n"
    
    if board.is_check():
        status += f"• {EMOJIS['check']} *¡Jaque!*\n"
    if board.is_game_over():
        if board.is_checkmate():
            status += f"• {EMOJIS['mate']} *¡Jaque mate!*\n"
            winner = "Negras" + EMOJIS['black_turn'] if board.turn else "Blancas" + EMOJIS['white_turn']
            status += f"• Ganador: {winner} 🏆\n"
        elif board.is_stalemate():
            status += f"• {EMOJIS['stalemate']} *Tablas por ahogado*\n"
        elif board.is_insufficient_material():
            status += f"• {EMOJIS['stalemate']} *Tablas por material insuficiente*\n"
        elif board.is_fivefold_repetition():
            status += f"• {EMOJIS['stalemate']} *Tablas por repetición*\n"
        elif board.is_seventyfive_moves():
            status += f"• {EMOJIS['stalemate']} *Tablas por regla de 75 movimientos*\n"
    
    return status

async def make_move_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja movimientos desde botones inline"""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    
    if game.board.is_game_over():
        await query.message.reply_text(
            f"{EMOJIS['warning']} La partida ya terminó\n"
            "Usa /reset para comenzar una nueva"
        )
        return
    
    # Obtener el movimiento del callback data
    if query.data.startswith("quick_move_"):
        move_uci = query.data.replace("quick_move_", "")
    else:
        move_uci = context.args[0] if context.args else None
    
    if not move_uci:
        await query.message.reply_text(
            f"{EMOJIS['error']} Movimiento no especificado"
        )
        return
    
    try:
        # Intentar interpretar como notación UCI o SAN
        try:
            move = chess.Move.from_uci(move_uci)
        except ValueError:
            move = game.board.parse_san(move_uci)
        
        # Validar movimiento legal
        if move not in game.board.legal_moves:
            await query.message.reply_text(
                f"{EMOJIS['error']} Movimiento ilegal\n"
                f"{EMOJIS['warning']} Usa /best para sugerencias válidas"
            )
            return
        
        # Realizar movimiento
        san_move = game.board.san(move)
        game.make_move(move)
        
        # Generar imagen del nuevo estado del tablero
        png_data = generate_board_image(game.board)
        
        # Botones después de mover
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['best_move']} Mejor Jugada", callback_data="best_move_menu"),
             InlineKeyboardButton(f"{EMOJIS['undo']} Deshacer", callback_data="undo_move_menu")],
            [InlineKeyboardButton(f"{EMOJIS['board']} Ver Tablero", callback_data="show_board")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        with io.BytesIO(png_data) as photo:
            photo.name = 'tablero.png'
            await query.message.reply_photo(
                photo=photo,
                caption=(
                    f"{EMOJIS['success']} *Movimiento aplicado:*\n"
                    f"• SAN: `{san_move}`\n"
                    f"• UCI: `{move.uci()}`\n"
                    f"• Turno actual: {'Blancas' + EMOJIS['white_turn'] if game.board.turn else 'Negras' + EMOJIS['black_turn']}"
                ),
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        
    except ValueError as e:
        await query.message.reply_text(
            f"{EMOJIS['error']} Movimiento inválido: {str(e)}\n"
            f"{EMOJIS['warning']} Usa notación UCI (e2e4) or SAN (Nf3)"
        )

async def best_move_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la solicitud de mejor jugada desde el menú"""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    
    if game.board.is_game_over():
        await query.message.reply_text(
            f"{EMOJIS['warning']} La partida ya terminó\n"
            "Usa /reset para comenzar una nueva"
        )
        return
    
    # Tiempo de análisis por defecto: 0.5 segundos
    analysis_time = 0.5
    
    try:
        with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
            result = engine.analyse(
                game.board,
                chess.engine.Limit(time=analysis_time),
                multipv=1
            )
            
            if not result or 'pv' not in result[0]:
                await query.message.reply_text(f"{EMOJIS['error']} No se pudo encontrar movimiento")
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
            
            # Botones para aplicar o descartar la jugada
            keyboard = [
                [InlineKeyboardButton(f"{EMOJIS['apply_move']} Aplicar Jugada", callback_data=f"apply_best_{best_move.uci()}")],
                [InlineKeyboardButton(f"{EMOJIS['undo']} Descartar", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            with io.BytesIO(png_data) as photo:
                photo.name = 'mejor_jugada.png'
                await query.message.reply_photo(
                    photo=photo,
                    caption=(
                        f"{EMOJIS['evaluation']} *Mejor jugada sugerida:*\n"
                        f"• SAN: `{san_move}`\n"
                        f"• UCI: `{best_move.uci()}`\n"
                        f"• Evaluación: {eval_str}\n"
                        f"• Tiempo análisis: {analysis_time}s"
                    ),
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            
    except Exception as e:
        logger.error(f"Error con Stockfish: {e}")
        await query.message.reply_text(f"{EMOJIS['error']} Error al analizar con Stockfish")

async def apply_best_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Aplica la mejor jugada desde el callback"""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    
    if game.board.is_game_over():
        await query.message.reply_text(
            f"{EMOJIS['warning']} La partida ya terminó\n"
            "Usa /reset para comenzar una nueva"
        )
        return
    
    # Obtener el movimiento del callback data
    move_uci = query.data.replace("apply_best_", "")
    move = chess.Move.from_uci(move_uci)
    
    # Aplicar movimiento
    san_move = game.board.san(move)
    game.make_move(move)
    
    # Generar imagen del nuevo estado
    png_data = generate_board_image(game.board)
    
    # Obtener evaluación para el nuevo estado
    analysis_time = 0.1
    try:
        with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
            new_result = engine.analyse(
                game.board,
                chess.engine.Limit(time=analysis_time),
                multipv=1
            )
            new_eval = format_evaluation(new_result[0]['score'])
    except:
        new_eval = "N/A"
    
    # Botones después de aplicar la jugada
    keyboard = [
        [InlineKeyboardButton(f"{EMOJIS['undo']} Deshacer", callback_data="undo_move_menu"),
         InlineKeyboardButton(f"{EMOJIS['board']} Ver Tablero", callback_data="show_board")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    with io.BytesIO(png_data) as photo:
        photo.name = 'tablero_actualizado.png'
        await query.message.reply_photo(
            photo=photo,
            caption=(
                f"{EMOJIS['success']} *Mejor jugada aplicada:*\n"
                f"• SAN: `{san_move}`\n"
                f"• UCI: `{move.uci()}`\n"
                f"• Nueva evaluación: {new_eval}\n"
                f"• Turno actual: {'Blancas' + EMOJIS['white_turn'] if game.board.turn else 'Negras' + EMOJIS['black_turn']}"
            ),
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

# ... (las funciones restantes mantienen la misma estructura pero se añaden botones inline donde sea apropiado)

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
    
    # Handler para menús inline
    application.add_handler(CallbackQueryHandler(handle_menu_selection))
    
    # Manejo de errores
    application.add_error_handler(error_handler)
    
    # Iniciar bot
    application.run_polling()
    logger.info("Bot iniciado correctamente")

if __name__ == "__main__":
    main()