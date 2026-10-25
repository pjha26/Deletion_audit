"""Small local multilingual intent model; training examples are authored, not dataset labels."""
import math
import re
import unicodedata
from collections import Counter

DELETE_EXAMPLES = [
    'Delete my account and all my personal information.',
    'Please erase my profile permanently.',
    'Close this account and remove its associated data.',
    'I request permanent account closure and data deletion.',
    'My deletion failed. Please complete it and check every copy.',
    'Remove the old profile still appearing in search after I deleted my account.',
    'I want my personal records removed from your systems.',
    'I changed my email. Delete records for both addresses.',
    'Please check that my data has been erased everywhere.',
    'My account is closed but an integration still sends my data. Finish deleting it.',
    'Anonymous statistics are fine; erase my account and identifying information.',
    'Delete my account but preserve records you are required to retain.',
    'Remove any remaining copy of my profile after account closure.',
    'Check whether my account was deleted and confirm the erasure.',
    'Verify the completed account deletion; ignore unrelated records.',
    'The same email is still recognized after deletion. Remove my profile.',
    'Please audit my previous deletion request and finish removing personal details.',
    'Supprimez mon compte et mes données personnelles.',
    'Je demande la suppression définitive de mon profil.',
    'Veuillez effacer les informations associées à mon ancien compte.',
    'Elimina mi cuenta y todos mis datos personales.',
    'Solicito la eliminación permanente de esta cuenta.',
    'La eliminación falló; comprueba los datos y completa la eliminación.',
    'Solicito a exclusão da minha conta e dos meus dados pessoais.',
    'Por favor apague permanentemente o meu perfil.',
    'Bitte löschen Sie mein Konto und meine persönlichen Daten.',
    'Ich beantrage die endgültige Löschung meines Benutzerkontos.',
    'Elimina definitivamente il mio account e i dati personali.',
    'Chiedo la cancellazione del profilo e delle informazioni personali.',
    'このアカウントと個人情報を完全に削除してください。',
    'メールアドレスに関連するアカウントの削除を依頼します。',
    '계정과 개인정보를 삭제해 주세요.',
    '개인정보 영구 삭제를 요청하며 계정을 해지합니다.',
    '계정 삭제 요청을 처리하고 결과를 알려주세요.',
    '이전 이메일과 현재 이메일에 연결된 개인정보를 지워 주세요.',
    '영구 삭제 후 남아 있는 개인정보가 없는지 확인해 주세요.',
    '请删除我的账户和所有个人信息。',
    'मेरा खाता और व्यक्तिगत जानकारी हटा दें।',
    'يرجى حذف حسابي وبياناتي الشخصية نهائيا',
    'Verwijder mijn account en alle persoonsgegevens.',
    'Usuń moje konto i dane osobowe.',
]
OTHER_EXAMPLES = [
    'Send me a copy of my information; keep my account open.',
    'I want a data export and do not want deletion.',
    'Do not delete my account. I need my invoices.',
    'Please change my email address.',
    'Correct the spelling of my surname.',
    'Update my phone number and leave the account active.',
    'Help me reset my password and log in.',
    'Unsubscribe me from advertising emails only.',
    'Remove me from marketing lists but keep my profile.',
    'What information do you hold about me?',
    'I need a portable copy of my account information.',
    'Please stop promotions. I am not asking to erase my account.',
    'I want receipts, purchase history and my account to remain available.',
    'How can I delete an account? Please explain without making changes.',
    'Cancel my order but keep my customer account.',
    'Ne supprimez pas mon compte; envoyez une copie de mes données.',
    'Corrigez mon numéro de téléphone sans supprimer mon profil.',
    'No eliminen mi cuenta; necesito una copia de mis facturas.',
    'Quiero cambiar mi dirección de correo y seguir usando la cuenta.',
    'Não exclua minha conta. Quero apenas uma cópia dos dados.',
    'Quero cancelar apenas os emails promocionais.',
    'Bitte mein Konto nicht löschen; nur meine Adresse korrigieren.',
    'Non cancellare il mio account. Inviami una copia dei dati.',
    'アカウントを削除せず、個人情報のコピーを送ってください。',
    '계정을 삭제하지 말고 이메일만 변경해 주세요.',
    '不要删除我的账户，只更新电话号码。',
    'मेरा खाता न हटाएं, केवल ईमेल बदलें।',
    'لا تحذف حسابي أريد نسخة من بياناتي فقط',
    'Verwijder mijn account niet; pas alleen mijn adres aan.',
    'Nie usuwaj konta, zmień tylko adres e-mail.',
]


def normalize(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text).casefold()).strip()


def features(text):
    text = ' ' + normalize(text) + ' '
    return Counter(text[i:i+n] for n in (3, 4, 5) for i in range(len(text)-n+1))


class IntentModel:
    # shortcut: authored examples do not cover every language or negation, expand with independently labeled requests before production use.
    name = 'authored-multilingual-char-ngram-naive-bayes-v1'

    def __init__(self):
        self.counts = [Counter(), Counter()]
        for label, examples in enumerate((OTHER_EXAMPLES, DELETE_EXAMPLES)):
            for text in examples:
                self.counts[label].update(features(text))
        self.vocab = set(self.counts[0]) | set(self.counts[1])
        self.totals = [sum(c.values()) + len(self.vocab) for c in self.counts]
        self.calls = 0

    def predict(self, text):
        self.calls += 1
        normalized = normalize(text)
        f = features(normalized)
        score = sum(min(count, 2) * (math.log((self.counts[1][key]+1)/self.totals[1]) -
                    math.log((self.counts[0][key]+1)/self.totals[0])) for key, count in f.items() if key in self.vocab)
        # Explicit prohibition overrides a statistical lexical resemblance to deletion.
        negative = re.search(r"(?:do not|don't|don’t|not asking (?:for|to)|not a request to)\s+(?:delete|close|erase|deletion)|"
                             r"(?:keep|leave)\b.{0,45}\b(?:active|open|as it is|in place)|"
                             r"marketing lists only|without removing|without making changes|"
                             r"ne supprimez pas|no eliminen|não exclua|nicht löschen|non cancellare|"
                             r"削除せず|削除しない|삭제하지|不要删除|لا تحذف", normalized)
        return {'authorized': False if negative else score > 0,
                'score': round(score, 4), 'method': 'explicit_prohibition' if negative else 'local_naive_bayes',
                'supported_fraction': round(sum(v for k, v in f.items() if k in self.vocab)/max(1, sum(f.values())), 3)}
