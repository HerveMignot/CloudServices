"""
Convert an audio file to a text with Google Speech API

Not so simple for long file...
- convert to FLAC if mp3 (most of the time)
- load to GS
- run a long recognition
- pool & get result

"""

import io
import os
import subprocess
import tempfile
import time

from google.cloud import speech
from google.cloud.speech import enums
from google.cloud.speech import types

from google.cloud import storage

# Define Google Cloud credentials & resources
from google.oauth2 import service_account
GOOGLE_CREDENTIALS = './keys/Podcasting-5266821f1f5b.json'
GOOGLE_CREDENTIALS = './keys/Podcasting-e15892bf4bc0.json'
GOOGLE_CREDENTIALS = './keys/Podcasting-dc102fb1d2fe.json'

GOOGLE_SCOPE = 'https://www.googleapis.com/auth/cloud-platform'
GOOGLE_BUCKET = 'podcasting'
GOOGLE_BUCKET_URI = 'gs://' + GOOGLE_BUCKET

# Locate ffmpeg runtime
# This is used to convert mp3 to flac as this audio format is supported by Google Cloud Speech
# Also, used to convert to a single channel
FFMPEG_RUNTINE = 'ffmpeg/bin/ffmpeg'

# Managing Google credentials
_credentials = None

def _get_credentials():
    """Get credentials for the project."""
    global _credentials
    if _credentials is None:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_CREDENTIALS
        _credentials = service_account.Credentials.from_service_account_file(GOOGLE_CREDENTIALS,
                                                                             scopes=[GOOGLE_SCOPE])
    return _credentials


def _convert_with_ffmpeg(filename):
    """Convert .mp3/* file to 1 channel flac."""
    # To be discussed: keep file open to get a hold on unique name, or close file for ffmpeg access.
    tmpfile = tempfile.mkstemp(suffix='.flac')
    os.close(tmpfile[0])
    subp = subprocess.run([FFMPEG_RUNTINE, '-i', filename, '-y', '-ac', '1', tmpfile[1]])
    if subp.returncode != 0:
        raise RuntimeError("FFMPEG conversion error: %d" % subp.returncode)
        
    # Return filename
    return tmpfile[1]


def _upload_to_gs(filename, delete=True, content='audio/flac'):
    """Upload file to Google Storage bucket."""
    client = storage.Client(credentials=_get_credentials())
    bucket = client.get_bucket(GOOGLE_BUCKET)
    blob = bucket.blob(os.path.basename(filename))
    blob.content_type = content
    blob.upload_from_filename(filename)
    if delete:
        os.remove(filename)
    return GOOGLE_BUCKET_URI + '/' + os.path.basename(filename)


# Dangerous to use basename on a uri? It works...
# Discussion here: https://stackoverflow.com/questions/1112545/os-path-basename-works-with-urls-why
def _delete_from_gs(uri):
    """Deletes blob file from Google Storage bucket."""
    storage_client = storage.Client(credentials=_get_credentials())
    bucket = storage_client.get_bucket(GOOGLE_BUCKET)
    blob = bucket.blob(os.path.basename(uri))
    blob.delete()


def convert_sound_file(filename, language='en-US', wait=1200, keep_on_gs=False):
    """
    Convert a sound file to a transcript using Google API.
    Files must be converted to FLAC encoding if they are not already.
    Big files have to be stored on a gs bucket to avoid time out.

    Args:
        filename (string): name of the file to convert
        language (string): language of voices in file (default: en-US)
        wait (int): time to wait of long running operations (if 0, use recognize, should be less 1 min text)

    Returns:
        Sound file transcript (first alternative) if wait > 0
        Operation name if wait == 0
    """
    working_filename = filename

    # Convert file if needed
    _, file_extension = os.path.splitext(filename)
    if file_extension is not '.flac':
        working_filename = _convert_with_ffmpeg(filename)

    # Upload file if necessary
    # Optimal size to be determined, always upload for now
    size = os.path.getsize(working_filename)
    uploaded = (size > 0)
    if uploaded:
        upload_uri = _upload_to_gs(working_filename, delete=(filename != working_filename))
        
    # Instantiates a Speech client using credentials
    client = speech.SpeechClient(credentials=_get_credentials())

    # Loads the audio into memory
    if uploaded:
        audio = types.RecognitionAudio(uri=upload_uri)
    else:
        with io.open(working_filename, 'rb') as audio_file:
            content = audio_file.read()
            audio = types.RecognitionAudio(content=content)

    config = types.RecognitionConfig(
        encoding=enums.RecognitionConfig.AudioEncoding.FLAC,
        language_code=language)

    print("URI:", upload_uri)
    # Detects speech in the audio file
    operation = client.long_running_recognize(config, audio)
    operation_name = operation.operation_name()
    if wait > 0:
        print("Operation:", operation_name)
        retry_count = wait // 10 + 1
        while retry_count > 0 and not operation.done():
            retry_count -= 1
            time.sleep(10)
            progress = operation.metadata().progress_percent
            print("Progress:", progress)

        if not operation.done():
            raise TimeoutError("Conversion not completed before end of retries")
        
        response = operation.result()
        transcript = ''
        for result in response.results:
            # Several alternatives could be proposed, but generally only one is available
            transcript += result.alternatives[0].transcript + '\n'

        if uploaded and not keep_on_gs:
            _delete_from_gs(upload_uri)
            
        return transcript
    
    else:
        return operation_name

def get_transcript_from_operation(operation_name):
    """
    Get transcription from operation name if conversion has been run without waiting for the result

    Args:
        operation_name (string): operation name as returned by API call

    Returns:
        Sound file transcript (first alternative)
    """
    # Instantiates a Speech client using credentials
    return "Not implemented yet"
    client = speech.SpeechClient(credentials=_get_credentials())
    operation = speech.Operation(client, name=operation_name)
    pass


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Convert sound file to text.',
        prog='convert2txt',
        usage='%(prog)s filename',
        )
    # Not yet functioning for retrieving from operation
    conversion_group = parser.add_argument_group('Conversion', 'Run file conversion on API')
    conversion_group.add_argument('soundfile', type=str, help='sound file name')
    conversion_group.add_argument('-l', '--language', type=str, help='language (default en-US)', default='en-US')
    conversion_group.add_argument('--nowait', action='store_true', help='do not wait for results, return operation name', default=False)
    conversion_group.add_argument('--keep', action='store_true', help='keep uploaded file in the bucket', default=False)
    retrieve_group = parser.add_argument_group('Retrieve', 'Retrieve results from API')
    retrieve_group.add_argument('--get', type=str, help='get results from operation', dest='operation_name', default=None)
    args = parser.parse_args()

    if args.operation_name is not None:
        returned = get_transcript_from_operation(args.operation_name)
        
    elif not os.path.isfile(args.soundfile):
        print('%s: file not found.' % args.soundfile)
        exit(-1)

    else:
        returned = convert_sound_file(  args.soundfile,
                                        language=args.language,
                                        wait=0 if args.nowait else 1200,
                                        keep_on_gs=args.keep,
                                        )
    #upload_to_gs(convert_with_ffmpeg(args.soundfile))

    # Default: output transcript
    print(returned)
