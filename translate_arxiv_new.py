import requests
import re  # 정규식을 사용하기 위해 추가
from bs4 import BeautifulSoup
import openai
import argparse
from datetime import datetime
import os

# Arxiv 주제 URL 생성 함수 (New submissions 페이지로 변경)
def get_arxiv_url(subject):
    base_url = "https://arxiv.org/list/"
    if subject == "RO":
        return base_url + "cs.RO/new"  # 로보틱스의 신규 제출
    elif subject == "CV":
        return base_url + "cs.CV/new"  # 컴퓨터 비전의 신규 제출
    else:
        raise ValueError(f"Invalid subject code: {subject}. Use 'RO' for Robotics or 'CV' for Computer Vision.")

# 논문 목록을 가져오는 함수 (특정 날짜 필터링은 하지 않고 모든 논문을 가져옴)
def get_paper_urls(base_url):
    response = requests.get(base_url)
    soup = BeautifulSoup(response.text, 'html.parser')

    # 논문 날짜를 포함한 정보 찾기
    date_tag = soup.find('h3')
    if date_tag:
        paper_date_str = date_tag.text.strip()

        # 정규식을 사용해 날짜만 추출
        match = re.search(r'New submissions for (.*) \(', paper_date_str)
        if match:
            paper_date_str = match.group(1).strip()
            # 날짜 추출 및 변환
            paper_date = datetime.strptime(paper_date_str, '%A, %d %B %Y').date()
        else:
            raise ValueError("Date format not recognized in: " + paper_date_str)
    else:
        raise ValueError("Date not found on the page")

    # 논문 링크 추출
    paper_links = soup.find_all('a', title="Abstract")
    paper_urls = ["https://arxiv.org" + link['href'] for link in paper_links]
    
    return paper_urls, paper_date

# 논문 페이지에서 제목과 초록을 추출하는 함수
def extract_title_and_abstract(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    # 논문 제목 추출
    title_tag = soup.find('h1', class_='title mathjax')
    title = title_tag.text.replace('Title:', '').strip() if title_tag else 'No title found'

    # 초록 추출
    abstract_block = soup.find('blockquote', class_='abstract mathjax')
    if abstract_block:
        abstract = abstract_block.text.replace('Abstract:', '').strip()
        return title, abstract
    return title, None

# OpenAI를 사용해 초록을 친근한 말투로 번역하는 함수
def translate_abstract(abstract, model):
    response = openai.ChatCompletion.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a robotics and computer vision researcher who explains and translates research abstracts to junior colleagues. Your role is to translate research abstracts accurately into Korean, in a way that is easy to understand for junior colleagues."},
            {"role": "user", "content": f"Translate the following research abstract into Korean in a casual but accurate manner. Do not add any greetings or extra comments. Simplify the language to make it easier to understand and use informal speech. Add paragraph breaks if necessary:\n\n{abstract}"}
        ],
        max_tokens=1024,
        temperature=0.7,
    )

    translation = response['choices'][0]['message']['content'].strip()
    return translation

# 번역 결과를 텍스트 파일로 저장하는 함수
def save_translation(filename, url, title, original_abstract, translated_abstract):
    # abs 부분을 pdf로 변환
    pdf_url = url.replace('/abs/', '/pdf/') + ".pdf"

    with open(filename, 'a', encoding='utf-8') as f:
        f.write(f"URL:\n{pdf_url}\n\n")
        f.write(f"Title: {title}\n\n")
        f.write(f"Original Abstract:\n{original_abstract}\n\n")
        f.write(f"Translated Abstract:\n{translated_abstract}\n\n")
        f.write("="*80 + "\n\n")

# 전체 프로세스를 실행하는 함수
def process_papers(base_url, output_file, model, num_max=None):
    # 논문 URL 리스트와 날짜 가져오기
    paper_urls, paper_date = get_paper_urls(base_url)

    # num_max 값이 None이면 모든 논문을 처리
    if num_max is None:
        num_max = len(paper_urls)

    counter = 0
    for url in paper_urls:
        counter += 1
        if counter > num_max:
            break

        try:
            # 각 논문에서 제목과 초록 추출
            title, abstract = extract_title_and_abstract(url)
            print(f"Title: {title}")
            print(f"Abstract: \n{abstract}")

            if abstract:
                print(f"Translating abstract from: {url} using model: {model}")
                # 초록을 번역
                translation = translate_abstract(abstract, model)

                # 터미널에 번역된 결과 출력
                print(f"Translated Abstract: \n{translation}\n")

                # 제목, 원문 초록과 번역된 초록을 파일에 저장
                save_translation(output_file, url, title, abstract, translation)
        except Exception as e:
            print(f"Error processing {url}: {e}")

    return paper_date

# 명령줄 인자를 처리하는 함수
def main():
    parser = argparse.ArgumentParser(description="Arxiv 논문 번역기")
    parser.add_argument('subject', type=str, help="번역할 주제를 선택하세요. 'RO'는 로보틱스, 'CV'는 컴퓨터 비전")
    parser.add_argument('model', type=str, help="사용할 OpenAI 모델을 선택하세요. 예: 'gpt-3.5-turbo', 'gpt-4'")
    parser.add_argument('api_key', type=str, help="OpenAI API 키를 입력하세요")
    parser.add_argument('--num_max', type=int, default=None, help="번역할 논문 개수 (기본값은 모든 논문)")
    args = parser.parse_args()

    # OpenAI API 키 설정
    openai.api_key = args.api_key

    try:
        # 주제에 맞는 Arxiv URL 가져오기
        base_url = get_arxiv_url(args.subject)

        # 논문을 처리하고, 논문 날짜 반환
        paper_date = None

        # 파일 이름에 날짜를 포함 (연-월-일 형식)
        paper_date_str = datetime.now().strftime('%Y-%m-%d')  # 기본 파일 이름 날짜 (현재 날짜)
        
        # 논문 페이지에서 날짜 추출
        paper_urls, paper_date = get_paper_urls(base_url)

        # 해당 날짜를 파일명에 추가
        if paper_date:
            paper_date_str = paper_date.strftime('%Y-%m-%d')

        output_dir = "daily-db"
        output_file = f"{output_dir}/translated_abstracts_{args.subject}_{paper_date_str}_{args.model}.txt"

        # 이미 번역된 파일이 존재하는지 확인
        if os.path.exists(output_file):
            print(f"Translation file for {paper_date_str} already exists. Skipping...")
            return  # 파일이 이미 있으면 종료

        # 논문을 처리
        process_papers(base_url, output_file, args.model, args.num_max)

        print(f"Finished processing. Translations saved in {output_file}")

    except ValueError as e:
        print(e)

# 실제로 실행하는 부분
if __name__ == "__main__":
    main()

