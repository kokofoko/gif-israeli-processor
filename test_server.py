import json, subprocess, tempfile, unittest
from pathlib import Path
from server import validate, normalize

class ProcessorTests(unittest.TestCase):
    def test_input_boundaries(self):
        self.assertEqual(validate({'videoId':'jNQXAC9IVRw','start':2,'end':5}), ('jNQXAC9IVRw',2,5))
        for data in [dict(videoId='../../etc/passwd',start=0,end=1),dict(videoId='jNQXAC9IVRw',start=0,end=20),dict(videoId='jNQXAC9IVRw',start=float('nan'),end=2),dict(videoId='jNQXAC9IVRw',start=True,end=2)]:
            with self.subTest(data=data), self.assertRaises(ValueError): validate(data)

    def test_real_encoding(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.mp4';target=Path(folder)/'clip.mp4'
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=640x360:rate=25','-t','4','-c:v','libx264','-threads','1',str(source)],check=True)
            normalize(source,target,2.5)
            info=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-show_streams','-of','json',str(target)]))
            self.assertAlmostEqual(float(info['format']['duration']),2.5,delta=.15)
            self.assertEqual(info['streams'][0]['width'],480)
            self.assertEqual(info['streams'][0]['codec_name'],'h264')

if __name__=='__main__': unittest.main()
