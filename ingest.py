import argparse
import hashlib
from pathlib import Path
import fitz
import time
from app.knowledge import ensure_index,embed
def chunk(text,size=1100,overlap=180):
    text="".join(text.split())
    step=size-overlap
    return[text[i:i+size] for i in range(0,len(text),step) if len(text[i:i+size])>80]
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--pdf",default='data/Gale Encyclopedia of Medicine Vol 1 2nd Edition - PDF Room.pdf')
    args=parser.parse_args()
    index=ensure_index()
    pdf=Path(args.pdf)
    with fitz.open(pdf) as docs:
        batch=[]
        for page_number ,page in enumerate(docs,start=1):
            for part,content in enumerate(chunk(page.get_text()),start=1):
                key=hashlib.sha256(f'{pdf.name}:{page_number}:{part}:{content}'.encode()).hexdigest()
                batch.append((key,content,{'page':page_number,'text':content,'file':pdf.name}))
                if len(batch)>=50:
                    vectors=embed([b[1] for b in batch])
                    index.upsert(vectors=[{'id':b[0],'values':v,'metadata':b[2]}for  b,v in zip(batch,vectors)])
            if page_number % 50==0:
                print(f'INDEXED PAGES:{page_number}/{len(docs)}',flush=True)
        if batch:
            vectors=embed([b[1] for b in batch])
            index.upsert(vectors=[{"id":b[0],'values':v,'metadata':b[2]}for b,v in zip(batch,vectors)])
            time.sleep(31)
    print("ingestion complete")
if __name__=="__main__" :main()