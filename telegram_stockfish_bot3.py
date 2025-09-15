import os
import logging
import chess
import chess.engine
import chess.svg
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import io
import cairosvg

TOKEN = os.getenv("TELEGRAM_TOKEN")
STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "stockfish/stockfish-exec")


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
    'undo': '↩️'
}

# Estado del juego por chat
games = {}

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
    """Maneja el comando /start con mensaje de bienvenida"""
    welcome_message = (
        f"{EMOJIS['K']} ¡Bienvenido al Bot de Ajedrez con Stockfish! {EMOJIS['k']}\n\n"
        "Comandos disponibles:\n"
        "• /start - Muestra este mensaje\n"
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
    
    await update.message.reply_text(welcome_message)

async def chess_board(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el tablero actual como imagen"""
    chat_id = update.effective_chat.id
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
            await update.message.reply_photo(photo=photo, caption=status)
            
    except Exception as e:
        logger.error(f"Error generando imagen del tablero: {e}")
        # Fallback a representación textual si hay error con la imagen
        board_str = str(game.board).replace(' ', '').replace('\n', '')
        await update.message.reply_text(
            f"{EMOJIS['error']} Error al generar imagen. Aquí está el tablero en texto:\n\n"
            f"`{board_str}`\n\n{status}",
            parse_mode='MarkdownV2'
        )

async def make_move(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Aplica un movimiento al tablero"""
    chat_id = update.effective_chat.id
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    
    if not context.args:
        await update.message.reply_text(
            f"{EMOJIS['error']} Debes especificar un movimiento\n"
            "Ejemplo: /move e2e4 o /move Nf3"
        )
        return
    
    if game.board.is_game_over():
        await update.message.reply_text(
            f"{EMOJIS['warning']} La partida ya terminó\n"
            "Usa /reset para comenzar una nueva"
        )
        return
    
    move_uci = context.args[0]
    
    try:
        # Intentar interpretar como notación UCI o SAN
        try:
            move = chess.Move.from_uci(move_uci)
        except ValueError:
            move = game.board.parse_san(move_uci)
        
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
                )
            )
        
    except ValueError as e:
        await update.message.reply_text(
            f"{EMOJIS['error']} Movimiento inválido: {str(e)}\n"
            f"{EMOJIS['warning']} Usa notación UCI (e2e4) or SAN (Nf3)"
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

async def best_move(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sugiere la mejor jugada usando Stockfish"""
    chat_id = update.effective_chat.id
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    
    if game.board.is_game_over():
        await update.message.reply_text(
            f"{EMOJIS['warning']} La partida ya terminó\n"
            "Usa /reset para comenzar una nueva"
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
                await update.message.reply_text(f"{EMOJIS['error']} No se pudo encontrar movimiento")
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
                await update.message.reply_photo(
                    photo=photo,
                    caption=(
                        f"{EMOJIS['evaluation']} Mejor jugada:\n"
                        f"• SAN: {san_move}\n"
                        f"• UCI: {best_move.uci()}\n"
                        f"• Evaluación: {eval_str}\n"
                        f"• Tiempo análisis: {analysis_time}s\n\n"
                        f"{EMOJIS['warning']} Usa /applybest para aplicar esta jugada"
                    )
                )
            
    except Exception as e:
        logger.error(f"Error con Stockfish: {e}")
        await update.message.reply_text(f"{EMOJIS['error']} Error al analizar con Stockfish")

async def apply_best_move(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Aplica la mejor jugada sugerida por Stockfish"""
    chat_id = update.effective_chat.id
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    
    if game.board.is_game_over():
        await update.message.reply_text(
            f"{EMOJIS['warning']} La partida ya terminó\n"
            "Usa /reset para comenzar una nueva"
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
                await update.message.reply_text(f"{EMOJIS['error']} No se pudo encontrar movimiento")
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
                await update.message.reply_photo(
                    photo=photo,
                    caption=(
                        f"{EMOJIS['success']} Mejor jugada aplicada:\n"
                        f"• SAN: {san_move}\n"
                        f"• UCI: {best_move.uci()}\n"
                        f"• Nueva evaluación: {new_eval}\n"
                        f"• Turno actual: {'Blancas' + EMOJIS['white_turn'] if game.board.turn else 'Negras' + EMOJIS['black_turn']}"
                    )
                )
            
    except Exception as e:
        logger.error(f"Error aplicando mejor movimiento: {e}")
        await update.message.reply_text(f"{EMOJIS['error']} Error al aplicar movimiento")

async def show_fen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la posición actual en formato FEN"""
    chat_id = update.effective_chat.id
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    await update.message.reply_text(f"`{game.board.fen()}`", parse_mode='MarkdownV2')

async def set_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Establece una posición personalizada mediante FEN"""
    chat_id = update.effective_chat.id
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    
    if not context.args:
        await update.message.reply_text(
            f"{EMOJIS['error']} Debes proporcionar una posición FEN\n"
            "Ejemplo: /position rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
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
                )
            )
    except ValueError as e:
        await update.message.reply_text(
            f"{EMOJIS['error']} FEN inválido: {str(e)}"
        )

async def undo_move(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deshace el último movimiento o varios movimientos"""
    chat_id = update.effective_chat.id
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    
    if not game.history:
        await update.message.reply_text(f"{EMOJIS['warning']} No hay movimientos para deshacer")
        return
    
    # Determinar cuántos movimientos deshacer
    num_moves = 1
    if context.args:
        try:
            num_moves = int(context.args[0])
            if num_moves < 1:
                await update.message.reply_text(f"{EMOJIS['error']} Debe ser un número positivo")
                return
        except ValueError:
            await update.message.reply_text(f"{EMOJIS['error']} Número inválido")
            return
    
    # Verificar que no se intenten deshacer más movimientos de los disponibles
    if num_moves > len(game.history):
        num_moves = len(game.history)
        await update.message.reply_text(
            f"{EMOJIS['warning']} Solo hay {num_moves} movimientos en el historial. "
            f"Deshaciendo {num_moves} movimientos."
        )
    
    # Deshacer movimientos
    moves_undone = game.undo_move(num_moves)
    
    # Generar imagen del tablero después de deshacer
    png_data = generate_board_image(game.board)
    
    with io.BytesIO(png_data) as photo:
        photo.name = 'tablero_deshacer.png'
        await update.message.reply_photo(
            photo=photo,
            caption=(
                f"{EMOJIS['undo']} Deshecho(s) {moves_undone} movimiento(s)\n"
                f"Turno: {'Blancas' + EMOJIS['white_turn'] if game.board.turn else 'Negras' + EMOJIS['black_turn']}\n"
                f"Movimientos restantes en historial: {len(game.history)}"
            )
        )

async def reset_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reinicia la partida a la posición inicial"""
    chat_id = update.effective_chat.id
    games[chat_id] = ChessGame()
    
    # Generar imagen del tablero inicial
    game = games[chat_id]
    png_data = generate_board_image(game.board)
    
    with io.BytesIO(png_data) as photo:
        photo.name = 'tablero_inicial.png'
        await update.message.reply_photo(
            photo=photo,
            caption=(
                f"{EMOJIS['success']} Partida reiniciada\n"
                f"Turno: Blancas{EMOJIS['white_turn']}"
            )
        )

async def evaluate_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Evalúa la posición actual con Stockfish"""
    chat_id = update.effective_chat.id
    if chat_id not in games:
        games[chat_id] = ChessGame()
    
    game = games[chat_id]
    
    if game.board.is_game_over():
        await update.message.reply_text(
            f"{EMOJIS['warning']} La partida ya terminó\n"
            "Usa /reset para comenzar una nueva"
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
                await update.message.reply_text(f"{EMOJIS['error']} No se pudo evaluar la posición")
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
                await update.message.reply_photo(
                    photo=photo,
                    caption=(
                        f"{EMOJIS['evaluation']} Evaluación de posición:\n"
                        f"• Resultado: {eval_str}\n"
                        f"• Profundidad: {depth}\n"
                        f"• Variación principal: {pv_str}\n"
                        f"• Turno: {'Blancas' + EMOJIS['white_turn'] if game.board.turn else 'Negras' + EMOJIS['black_turn']}"
                    )
                )
            
    except Exception as e:
        logger.error(f"Error en evaluación: {e}")
        await update.message.reply_text(f"{EMOJIS['error']} Error al evaluar posición")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja errores no capturados"""
    logger.error(f"Error: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            f"{EMOJIS['error']} Error interno del bot\n"
            "Por favor, intenta nuevamente"
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
    
    # Manejo de errores
    application.add_error_handler(error_handler)
    
    # Iniciar bot
    application.run_polling()
    logger.info("Bot iniciado correctamente")

if __name__ == "__main__":
    main()
