from fastapi import FastAPI, File, UploadFile, HTTPException
import uvicorn
import tempfile
import subprocess
import os

app = FastAPI()

@app.post("/process-audio/")
async def process_audio(file: UploadFile = File(...)):
    try:
        if file.content_type != 'audio/ogg' and not file.filename.endswith('.ogg'):
            raise HTTPException(status_code=400, detail="Tipo de arquivo inválido. Apenas arquivos OGG são aceitos.")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_ogg_file:
            temp_ogg_file.write(await file.read())
            temp_ogg_file_path = temp_ogg_file.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio_file:
            temp_audio_file_path = temp_audio_file.name

        # Usar subprocess para chamar o ffmpeg para conversão
        ffmpeg_command = [
            'ffmpeg',
            '-y',  
            '-i', temp_ogg_file_path,
            '-acodec', 'libmp3lame',
            temp_audio_file_path
        ]

        ffmpeg_process = subprocess.run(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if ffmpeg_process.returncode != 0:
            error_message = ffmpeg_process.stderr.decode()
            raise HTTPException(status_code=500, detail=f"Erro ao converter o arquivo de áudio: {error_message}")


        import requests

        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise HTTPException(status_code=500, detail="Chave da API da OpenAI não encontrada.")

        with open(temp_audio_file_path, 'rb') as audio_file:
            files = {
                'file': ('audio.mp3', audio_file, 'audio/mpeg')
            }
            data = {
                'model': 'whisper-1',
                'language': 'pt'  
            }
            headers = {
                'Authorization': f'Bearer {openai_api_key}'
            }

            response = requests.post(
                'https://api.openai.com/v1/audio/transcriptions',
                headers=headers,
                data=data,
                files=files
            )

        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Erro ao transcrever o áudio: {response.text}")

        transcription = response.json()['text']

        prompt = f"Crie uma lista de tarefas a partir do seguinte texto:\n\n{transcription}"

        # Usar a API ChatCompletion da OpenAI para gerar a tasklist
        import openai
        openai.api_key = openai_api_key

        completion = openai.ChatCompletion.create(
            model='gpt-3.5-turbo',
            messages=[
                {'role': 'user', 'content': prompt}
            ]
        )

        task_list = completion.choices[0].message.content.strip()

        # Limpar arquivos temporários
        os.remove(temp_ogg_file_path)
        os.remove(temp_audio_file_path)

        return {'task_list': task_list}

    except Exception as e:
        if 'temp_ogg_file_path' in locals() and os.path.exists(temp_ogg_file_path):
            os.remove(temp_ogg_file_path)
        if 'temp_audio_file_path' in locals() and os.path.exists(temp_audio_file_path):
            os.remove(temp_audio_file_path)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "_main_":
    uvicorn.run(app, host="0.0.0.0")